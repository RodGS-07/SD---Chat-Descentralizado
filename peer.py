import socket
import time
import json
from threading import Thread
import atexit
import signal
import sys

class Peer:
    def __init__(self, nome, ip, porta):
        self.nome = nome
        self.ip = ip
        self.porta = porta
        self.id = None
        self.coordenador = False
        self.peers = []  # lista de (ip, porta)
        self.mapa_ids = {}      # mapeia (ip, porta) -> id
        self.mapa_nomes = {}    # mapeia (ip, porta) -> nome
        self.proximo_id = 1
        self.ultima_atividade = {}
        self.server_socket = None
        self.coordenador_atual = None
        self.em_eleicao = False

    # ============================================================
    # SERVIDOR
    # ============================================================
    def inicia_servidor(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.ip, self.porta))
        self.server_socket.listen(5)

        print(f"[SERVIDOR] {self.nome} ouvindo em {self.ip}:{self.porta}")

        while True:
            client_socket, _ = self.server_socket.accept()
            try:
                data = client_socket.recv(2048)
                msg = data.decode('utf-8')
                self.tratar_mensagem(msg, client_socket)
            except Exception as e:
                print(f"[ERRO SERVIDOR] {e}")
            finally:
                client_socket.close()

    # ============================================================
    # TRATAMENTO DE MENSAGENS
    # ============================================================
    def tratar_mensagem(self, msg, conn):
        if msg.startswith("JOIN "):
            _, ip, porta, nome = msg.split()
            porta = int(porta)
            novo_peer = (ip, porta)

            if novo_peer not in self.peers:
                self.peers.append(novo_peer)
                print(f"[SISTEMA] Novo peer adicionado: {nome} ({ip}:{porta})")

                # Atribui ID único
                if novo_peer not in self.mapa_ids:
                    novo_id = self.proximo_id
                    self.mapa_ids[novo_peer] = novo_id
                    self.proximo_id += 1
                else:
                    novo_id = self.mapa_ids[novo_peer]

                # Salva nome
                self.mapa_nomes[novo_peer] = nome

                print(f"[SISTEMA] Atribuído ID {novo_id} a {nome} ({ip}:{porta})")

            resposta = {"id": self.mapa_ids[novo_peer], "peers": self.peers}
            conn.send(json.dumps(resposta).encode('utf-8'))

            # Notifica todos sobre o novo peer e envia mapas
            self.notificar_peers(novo_peer)
            self.enviar_mapas_para_peers()

        elif msg.startswith("UPDATE "):
            _, json_lista = msg.split(" ", 1)
            nova_lista = [tuple(p) for p in json.loads(json_lista)]

            antigos = set(self.peers)
            novos = set(nova_lista)
            removidos = antigos - novos
            self.peers = nova_lista

            if removidos:
                for ip, porta in removidos:
                    nome_removido = self.mapa_nomes.get((ip, porta), "Desconhecido")
                    print(f"[SISTEMA] Peer removido: {nome_removido} ({ip}:{porta})")
                    self.mapa_nomes.pop((ip, porta), None)
            else:
                print("[SISTEMA] Lista de peers atualizada.")

        elif msg.startswith("HEARTBEAT "):
            _, ip, porta = msg.split()
            porta = int(porta)
            self.ultima_atividade[(ip, porta)] = time.time()

        elif msg.startswith("ELECTION "):
            self.tratar_eleicao(msg)

        elif msg.startswith("COORDINATOR "):
            self.tratar_novo_coordenador(msg)

        elif msg.startswith("MAP_UPDATE "):
            _, json_dados = msg.split(" ", 1)
            try:
                dados = json.loads(json_dados)
                self.mapa_ids = {tuple(eval(k)): v for k, v in dados.get("ids", {}).items()}
                self.mapa_nomes = {tuple(eval(k)): v for k, v in dados.get("nomes", {}).items()}
                print(f"[SISTEMA] Mapas de IDs e nomes atualizados.")
            except Exception as e:
                print(f"[ERRO] Falha ao processar MAP_UPDATE: {e}")

        elif msg.startswith("EXIT "):
            _, ip, porta, nome = msg.split()
            porta = int(porta)
            peer_removido = (ip, porta)

            # Coordenador não deve anunciar a própria saída
            if peer_removido == (self.ip, self.porta):
                return

            if peer_removido in self.peers:
                self.peers.remove(peer_removido)
                print(f"[SISTEMA] Peer saiu: {nome} ({ip}:{porta})")
                if self.coordenador:
                    self.notificar_peers(peer_removido)

        else:
            print(f"\n> {msg}")

    # ============================================================
    # CLIENTE
    # ============================================================
    def cliente(self, ip, porta, mensagem, wait_response=False):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((ip, porta))
            s.send(mensagem.encode('utf-8'))

            if wait_response:
                resp = s.recv(4096).decode('utf-8')
                return resp
        except Exception:
            return None
        finally:
            if s:
                s.close()

    # ============================================================
    # NOTIFICAÇÃO
    # ============================================================
    def notificar_peers(self, novo_peer):
        lista_serializada = json.dumps(self.peers)
        msg = f"UPDATE {lista_serializada}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()

    def enviar_mapas_para_peers(self):
        """Envia mapas de IDs e nomes para todos os peers."""
        try:
            dados = {
                "ids": {str(k): v for k, v in self.mapa_ids.items()},
                "nomes": {str(k): v for k, v in self.mapa_nomes.items()},
            }
            msg = f"MAP_UPDATE {json.dumps(dados)}"
            for ip, porta in self.peers:
                if (ip, porta) != (self.ip, self.porta):
                    Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()
            print("[SISTEMA] Mapas de IDs e nomes enviados aos peers.")
        except Exception as e:
            print(f"[ERRO] Falha ao enviar mapas: {e}")

    # ============================================================
    # ELEIÇÃO (BULLY)
    # ============================================================
    def iniciar_eleicao(self):
        if self.em_eleicao or self.id is None:
            return

        self.em_eleicao = True
        print("[ELEIÇÃO] Coordenador inativo. Iniciando eleição...")

        candidatos = [
            (ip, porta)
            for (ip, porta) in self.peers
            if self.mapa_ids.get((ip, porta), -1) > self.id
        ]
        recebeu_resposta = False

        for ip, porta in candidatos:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((ip, porta))
                s.send(f"ELECTION {self.id}".encode('utf-8'))
                s.close()
                recebeu_resposta = True
            except:
                pass

        if not recebeu_resposta:
            print(f"[ELEIÇÃO] Nenhum peer com ID maior respondeu. {self.nome} torna-se coordenador.")
            self.coordenador = True
            self.coordenador_atual = (self.ip, self.porta)
            self.recalcular_ids()
            self.anunciar_coordenador()
            Thread(target=self.enviar_heartbeat_coordenador, daemon=True).start()
        else:
            print("[ELEIÇÃO] Esperando peers de ID maior decidirem...")

    def recalcular_ids(self):
        print("[SISTEMA] Recalculando IDs após eleição...")
        novos_ids = {}
        maior_id = -1
        for peer in self.peers:
            if peer in self.mapa_ids:
                pid = self.mapa_ids[peer]
            else:
                pid = len(novos_ids)
            novos_ids[peer] = pid
            if pid > maior_id:
                maior_id = pid
        if (self.ip, self.porta) not in novos_ids:
            novos_ids[(self.ip, self.porta)] = 0
        self.mapa_ids = novos_ids
        self.proximo_id = maior_id + 1
        print(f"[SISTEMA] IDs recalculados. Próximo ID disponível: {self.proximo_id}")

    def tratar_eleicao(self, msg):
        _, id_origem = msg.split()
        id_origem = int(id_origem)
        if self.id > id_origem:
            print(f"[ELEIÇÃO] Recebi eleição de ID menor ({id_origem}). Meu ID {self.id} é maior.")
            Thread(target=self.iniciar_eleicao, daemon=True).start()

    def anunciar_coordenador(self):
        msg = f"COORDINATOR {self.ip} {self.porta} {self.nome}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()
        print(f"[ELEIÇÃO] {self.nome} ({self.ip}:{self.porta}) é o novo coordenador!")

    def tratar_novo_coordenador(self, msg):
        _, ip, porta, nome = msg.split()
        self.coordenador = False
        self.coordenador_atual = (ip, int(porta))
        self.em_eleicao = False
        print(f"[ELEIÇÃO] Novo coordenador eleito: {nome} ({ip}:{porta})")

    # ============================================================
    # HEARTBEAT
    # ============================================================
    def enviar_heartbeat_coordenador(self):
        while self.coordenador:
            for ip, porta in list(self.peers):
                if (ip, porta) != (self.ip, self.porta):
                    self.cliente(ip, porta, f"HEARTBEAT {self.ip} {self.porta}")
            time.sleep(5)

    def enviar_heartbeat_peer(self):
        while not self.coordenador:
            if self.coordenador_atual:
                ip, porta = self.coordenador_atual
                self.cliente(ip, porta, f"HEARTBEAT {self.ip} {self.porta}")
            time.sleep(5)

    # ============================================================
    # MONITORAMENTO
    # ============================================================
    def monitorar_coordenador(self):
        while True:
            if self.coordenador_atual:
                ultimo = self.ultima_atividade.get(self.coordenador_atual)
                if ultimo and time.time() - ultimo > 15:
                    print("[ALERTA] Coordenador inativo detectado!")
                    if self.coordenador_atual in self.peers:
                        self.peers.remove(self.coordenador_atual)
                    time.sleep(2)
                    self.iniciar_eleicao()
            time.sleep(5)

    # ============================================================
    # INICIALIZAÇÃO
    # ============================================================
    def iniciar_rede(self):
        if not self.peers:
            self.coordenador = True
            self.id = 0
            self.coordenador_atual = (self.ip, self.porta)
            self.mapa_ids[(self.ip, self.porta)] = self.id
            self.mapa_nomes[(self.ip, self.porta)] = self.nome
            self.peers.append((self.ip, self.porta))
            print(f"[SISTEMA] {self.nome} é o coordenador da rede (ID 0).")
            Thread(target=self.enviar_heartbeat_coordenador, daemon=True).start()
        else:
            coord_ip, coord_port = self.peers[0]
            msg = f"JOIN {self.ip} {self.porta} {self.nome}"
            resposta = self.cliente(coord_ip, coord_port, msg, wait_response=True)
            if resposta:
                try:
                    dados = json.loads(resposta)
                    self.id = dados.get("id")
                    self.peers = [tuple(p) for p in dados.get("peers", [])]
                    self.coordenador_atual = (coord_ip, coord_port)
                    print(f"[SISTEMA] ID atribuído: {self.id}.")
                except Exception as e:
                    print(f"[ERRO] Resposta inválida do coordenador: {e}")
            Thread(target=self.enviar_heartbeat_peer, daemon=True).start()
            Thread(target=self.monitorar_coordenador, daemon=True).start()

    # ============================================================
    # INTERFACE
    # ============================================================
    def iniciar(self):
        Thread(target=self.inicia_servidor, daemon=True).start()
        time.sleep(1)

        opcao = input("Deseja informar um coordenador existente? (s/n): ").strip().lower()
        if opcao == "s":
            porta = int(input("Porta do coordenador: "))
            self.peers.append(('localhost', porta))

        self.iniciar_rede()

        time.sleep(1)
        print("\n[SISTEMA] Chat iniciado!\nDigite 'LIST' para ver peers ou 'EXIT' para sair\n")
        while True:
            entrada = input("")
            if entrada == "EXIT":
                break
            elif entrada == "LIST":
                for peer in self.peers:
                    nome = self.mapa_nomes.get(peer, "Desconhecido")
                    print(f"{nome} -> {peer}")
            else:
                self.broadcast(entrada)

    # ============================================================
    # BROADCAST
    # ============================================================
    def broadcast(self, mensagem):
        for ip, porta in self.peers:
            Thread(target=self.cliente,
                   args=(ip, porta, f"{self.nome} [{self.id}]: {mensagem}"),
                   daemon=True).start()

    # ============================================================
    # ENCERRAMENTO
    # ============================================================
    def encerrar(self):
        print(f"\n[SISTEMA] {self.nome} encerrando...")
        msg = f"EXIT {self.ip} {self.porta} {self.nome}"

        # Coordenador não anuncia sua própria saída
        if self.coordenador:
            print("[SISTEMA] Coordenador encerrando — saída será detectada por falha de heartbeat.")
            return

        for ip, porta in list(self.peers):
            if (ip, porta) != (self.ip, self.porta):
                try:
                    self.cliente(ip, porta, msg)
                except:
                    pass
        print("[SISTEMA] Mensagem de saída enviada.")

# ============================================================
# MAIN
# ============================================================
def main():
    nome, porta_str = input("Digite seu nome e porta local (<nome> <porta>): ").split()
    porta = int(porta_str)
    p = Peer(nome, "localhost", porta)

    def sair_graciosamente(*args):
        p.encerrar()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, sair_graciosamente) # kill PID
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, sair_graciosamente)  # Ctrl+C
    finally:
        atexit.register(p.encerrar)
    # signal.signal(signal.SIGINT, sair_graciosamente)  # Ctrl+C
    # signal.signal(signal.SIGTERM, sair_graciosamente) # kill PID
    # atexit.register(p.encerrar)

    p.iniciar()

if __name__ == "__main__":
    main()
