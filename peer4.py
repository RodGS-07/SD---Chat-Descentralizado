import socket
import time
import json
from threading import Thread

class Peer:
    def __init__(self, nome, ip, porta):
        self.nome = nome
        self.ip = ip
        self.porta = porta
        self.id = None
        self.coordenador = False
        self.peers = []  # lista de (ip, porta)
        self.mapa_ids = {}  # mapeia (ip, porta) -> id
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
            _, ip, porta = msg.split()
            porta = int(porta)
            novo_peer = (ip, porta)

            if novo_peer not in self.peers:
                self.peers.append(novo_peer)
                print(f"[SISTEMA] Novo peer adicionado: {ip}:{porta}")

                # Atribui ID único e evita duplicação de IDs
                if novo_peer not in self.mapa_ids:
                    novo_id = self.proximo_id
                    self.mapa_ids[novo_peer] = novo_id
                    self.proximo_id += 1
                else:
                    novo_id = self.mapa_ids[novo_peer]
                print(f"[SISTEMA] Atribuído ID {novo_id} a {ip}:{porta}")

            resposta = {"id": self.mapa_ids[novo_peer], "peers": self.peers}
            conn.send(json.dumps(resposta).encode('utf-8'))
            self.notificar_peers(novo_peer)

        elif msg.startswith("UPDATE "):
            _, json_lista = msg.split(" ", 1)
            self.peers = [tuple(p) for p in json.loads(json_lista)]
            print(f"[SISTEMA] Lista de peers atualizada ({len(self.peers)}).")

        elif msg.startswith("HEARTBEAT "):
            _, ip, porta = msg.split()
            porta = int(porta)
            self.ultima_atividade[(ip, porta)] = time.time()

        elif msg.startswith("ELECTION "):
            self.tratar_eleicao(msg)

        elif msg.startswith("COORDINATOR "):
            self.tratar_novo_coordenador(msg)

        elif msg.startswith("EXIT "):
            _, ip, porta = msg.split()
            porta = int(porta)
            peer_removido = (ip, porta)
            if peer_removido in self.peers:
                self.peers.remove(peer_removido)
                print(f"[SISTEMA] Peer saiu: {ip}:{porta}")
                if self.coordenador:
                    self.notificar_peers(peer_removido)

        else:
            print(f"\n> {msg}")

    # ============================================================
    # CLIENTE
    # ============================================================
    def cliente(self, ip, porta, mensagem, wait_response=False):
        """
        Envia mensagem para ip:porta.
        Se wait_response==True (usado para JOIN), aguarda e retorna a resposta (string).
        """
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)  # timeout razoável para operações de JOIN
            s.connect((ip, porta))
            s.send(mensagem.encode('utf-8'))

            if wait_response:
                # aguarda resposta (por ex. JSON com id e peers)
                resp = s.recv(4096).decode('utf-8')
                return resp

        except Exception as e:
            # opcional: print(f"[ERRO CLIENTE] {e}")
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

    # ============================================================
    # --- ELEIÇÃO (BULLY) ---
    # ============================================================
    def iniciar_eleicao(self):
        """Inicia o processo de eleição Bully."""
        if self.em_eleicao:
            return  # já em eleição
        
        if self.id is None:
            # ainda não temos id (JOIN não concluído) -> não iniciar eleição
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

            # Recalcular IDs e o próximo ID disponível
            self.recalcular_ids()

            self.anunciar_coordenador()
            Thread(target=self.enviar_heartbeat_coordenador, daemon=True).start()

        else:
            print("[ELEIÇÃO] Esperando peers de ID maior decidirem...")

    def recalcular_ids(self):
        """
        Reconstroi o mapa de IDs e define o próximo ID disponível
        com base nos peers atuais conhecidos.
        """
        print("[SISTEMA] Recalculando IDs após eleição...")

        # Recria o mapa de IDs baseado no que o peer sabe
        # Caso o coordenador tenha um mapa prévio, ele mantém os conhecidos
        novos_ids = {}
        maior_id = -1

        for peer in self.peers:
            print(f"peer = {peer}")
            # Se o peer já tinha ID registrado, mantém
            if peer in self.mapa_ids:
                pid = self.mapa_ids[peer]
                print("if")
            else:
                # Caso contrário, atribui temporariamente um ID crescente
                pid = len(novos_ids)
                print("else")
            novos_ids[peer] = pid
            print(f"pid = {pid}; maior_id = {maior_id}")
            if pid > maior_id:
                maior_id = pid

        # Garante que o coordenador tenha ID 0 se for o primeiro
        if (self.ip, self.porta) not in novos_ids:
            novos_ids[(self.ip, self.porta)] = 0
            if maior_id < 0:
                maior_id = 0

        self.mapa_ids = novos_ids
        self.proximo_id = maior_id + 1

        print(f"[SISTEMA] IDs recalculados. Próximo ID disponível: {self.proximo_id}")

    def tratar_eleicao(self, msg):
        """Responde a pedidos de eleição de peers com ID menor."""
        _, id_origem = msg.split()
        id_origem = int(id_origem)
        if self.id > id_origem:
            print(f"[ELEIÇÃO] Recebi eleição de ID menor ({id_origem}). Meu ID {self.id} é maior.")
            Thread(target=self.iniciar_eleicao, daemon=True).start()

    def anunciar_coordenador(self):
        """Anuncia o novo coordenador a todos."""
        msg = f"COORDINATOR {self.ip} {self.porta}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()
        print(f"[ELEIÇÃO] {self.nome} ({self.ip}:{self.porta}) é o novo coordenador!")

    def tratar_novo_coordenador(self, msg):
        """Recebe o novo coordenador eleito."""
        _, ip, porta = msg.split()
        self.coordenador = False
        self.coordenador_atual = (ip, int(porta))
        self.em_eleicao = False
        print(f"[ELEIÇÃO] Novo coordenador eleito: {ip}:{porta}")

    # ============================================================
    # HEARTBEAT (bidirecional)
    # ============================================================
    def enviar_heartbeat_coordenador(self):
        """Coordenador envia heartbeats periódicos para todos."""
        while self.coordenador:
            for ip, porta in list(self.peers):
                if (ip, porta) != (self.ip, self.porta):
                    try:
                        self.cliente(ip, porta, f"HEARTBEAT {self.ip} {self.porta}")
                    except:
                        pass
            time.sleep(5)

    def enviar_heartbeat_peer(self):
        """Peers enviam heartbeats para o coordenador."""
        while not self.coordenador:
            if self.coordenador_atual:
                ip, porta = self.coordenador_atual
                try:
                    self.cliente(ip, porta, f"HEARTBEAT {self.ip} {self.porta}")
                except:
                    print("[ERRO] Falha ao enviar heartbeat ao coordenador.")
            time.sleep(5)

    # ============================================================
    # MONITORAMENTO DE COORDENADOR
    # ============================================================
    def monitorar_coordenador(self):
        """Detecta falha no coordenador."""
        while True:
            if self.coordenador_atual:
                ultimo = self.ultima_atividade.get(self.coordenador_atual)
                if ultimo is None:
                    # ainda não recebemos o primeiro heartbeat — esperar
                    time.sleep(1)
                    continue
                if time.time() - ultimo > 10:
                    print("[ALERTA] Coordenador inativo detectado!")
                    if self.coordenador_atual in self.peers:
                        self.peers.remove(self.coordenador_atual)
                    self.iniciar_eleicao()
            time.sleep(5)

    # ============================================================
    # INICIALIZAÇÃO
    # ============================================================
    def iniciar_rede(self):
        if not self.peers:
            # Sou o primeiro peer — serei o coordenador
            self.coordenador = True
            self.id = 0
            self.coordenador_atual = (self.ip, self.porta)
            self.mapa_ids[(self.ip, self.porta)] = self.id
            self.peers.append((self.ip, self.porta))
            print(f"[SISTEMA] {self.nome} é o coordenador da rede (ID 0).")
            Thread(target=self.enviar_heartbeat_coordenador, daemon=True).start()

        else:
            coord_ip, coord_port = self.peers[0]
            msg = f"JOIN {self.ip} {self.porta}"
            # usa cliente com espera por resposta; recebe JSON com 'id' e 'peers'
            resposta = self.cliente(coord_ip, coord_port, msg, wait_response=True)
            if resposta:
                try:
                    dados = json.loads(resposta)
                    self.id = dados.get("id")
                    # converte lista de listas em lista de tuplas
                    self.peers = [tuple(p) for p in dados.get("peers", [])]
                    # registra coordenador atual explicitamente
                    self.coordenador_atual = (coord_ip, coord_port)
                    print(f"[SISTEMA] ID atribuído: {self.id}. Peers: {self.peers}")
                except Exception as e:
                    print(f"[ERRO] Resposta inválida do coordenador: {e}")
                    # fallback: manter comportamento anterior (não virar coordenador)
                    self.coordenador_atual = (coord_ip, coord_port)
            else:
                print("[ERRO] Não foi possível receber resposta do coordenador no JOIN.")
                # decide comportamento: abortar, tentar outro coordenador, ou continuar como standalone.
                # aqui vamos apenas definir coordenador_atual e prosseguir (mas sem id)
                self.coordenador_atual = (coord_ip, coord_port)

            # só após obter id (ou ao menos coordenador_atual) iniciamos heartbeats e monitor
            Thread(target=self.enviar_heartbeat_peer, daemon=True).start()
            Thread(target=self.monitorar_coordenador, daemon=True).start()

    # ============================================================
    # INTERFACE
    # ============================================================
    def iniciar(self):
        Thread(target=self.inicia_servidor, daemon=True).start()

        opcao = input("Deseja informar um coordenador existente? (s/n): ").strip().lower()
        if opcao == "s":
            ip = input("IP do coordenador: ")
            porta = int(input("Porta do coordenador: "))
            self.peers.append((ip, porta))

        self.iniciar_rede()

        print("\n[SISTEMA] Chat iniciado!")
        while True:
            entrada = input("")
            if entrada == "EXIT":
                print("[SISTEMA] Saindo...")
                break
            else:
                self.broadcast(entrada)

    # ============================================================
    # BROADCAST
    # ============================================================
    def broadcast(self, mensagem):
        for ip, porta in self.peers:
            Thread(
                target=self.cliente,
                args=(ip, porta, f"{self.nome} [{self.id}]: {mensagem}"),
                daemon=True
            ).start()


# ============================================================
# MAIN
# ============================================================
def main():
    entrada = input("Digite seu nome e porta local (<nome> <porta>): ")
    nome, porta = entrada.split()
    p = Peer(nome, "localhost", int(porta))
    p.iniciar()

if __name__ == "__main__":
    main()
