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

    # ------------------------------
    # Servidor do peer
    # ------------------------------
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

    # ------------------------------
    # Tratamento de mensagens recebidas
    # ------------------------------
    def tratar_mensagem(self, msg, conn):
        if msg.startswith("JOIN "):
            # Novo peer pedindo para entrar
            _, ip, porta = msg.split()
            porta = int(porta)
            novo_peer = (ip, porta)

            if novo_peer not in self.peers:
                self.peers.append(novo_peer)
                print(f"[SISTEMA] Novo peer adicionado: {ip}:{porta}")

                # Gera um ID único para o novo peer
                novo_id = self.proximo_id
                self.mapa_ids[novo_peer] = novo_id
                self.proximo_id += 1
                print(f"[SISTEMA] Atribuído ID {novo_id} para o peer {ip}:{porta}")

            # Prepara resposta com ID e lista de peers
            resposta = {
                "id": self.mapa_ids[novo_peer],
                "peers": self.peers
            }
            conn.send(json.dumps(resposta).encode('utf-8'))

            # Notifica os outros peers sobre o novo
            self.notificar_peers(novo_peer)

        elif msg.startswith("UPDATE "):
            # Recebe atualização da lista
            try:
                _, json_lista = msg.split(" ", 1)
                self.peers = json.loads(json_lista)
                print(f"[SISTEMA] Lista de peers atualizada ({len(self.peers)}):")
                for ip, porta in self.peers:
                    print(f" - {ip}:{porta}")
            except Exception as e:
                print(f"[ERRO UPDATE] {e}")

        elif msg.startswith("HEARTBEAT "):
            # Atualiza último heartbeat
            _, ip, porta = msg.split()
            porta = int(porta)
            self.ultima_atividade[(ip, porta)] = time.time()

        elif msg.startswith("EXIT "):
            # Um peer está saindo da rede
            _, ip, porta = msg.split()
            porta = int(porta)
            peer_removido = (ip, porta)

            if peer_removido in self.peers:
                self.peers.remove(peer_removido)
                print(f"[SISTEMA] Peer saiu da rede: {ip}:{porta}")

                # Se for o coordenador, notifica os demais peers
                if self.coordenador:
                    print("[COORDENADOR] Atualizando lista de peers após saída...")
                    self.notificar_peers(peer_removido)

        else:
            # Mensagem normal
            print(f"\n> {msg}")

    # ------------------------------
    # Cliente envia mensagens
    # ------------------------------
    def cliente(self, ip, porta, mensagem):
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((ip, porta))
            client_socket.send(mensagem.encode('utf-8'))

            # Se for um JOIN, espera resposta com lista e ID
            if mensagem.startswith("JOIN "):
                resposta = client_socket.recv(2048).decode('utf-8')
                dados = json.loads(resposta)
                self.id = dados["id"]
                self.peers = dados["peers"]

                print(f"[SISTEMA] ID atribuído pelo coordenador: {self.id}")
                print(f"[SISTEMA] Lista de peers recebida ({len(self.peers)}):")
                for ip, porta in self.peers:
                    print(f" - {ip}:{porta}")

        except Exception as e:
            print(f"[ERRO] Falha ao enviar para {ip}:{porta} -> {e}")
        finally:
            client_socket.close()

    # ------------------------------
    # Notifica todos os peers da rede
    # ------------------------------
    def notificar_peers(self, novo_peer):
        lista_serializada = json.dumps(self.peers)
        msg = f"UPDATE {lista_serializada}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()

    # ------------------------------
    # Broadcast (envia mensagens normais)
    # ------------------------------
    def broadcast(self, mensagem):
        for ip, porta in self.peers:
            Thread(
                target=self.cliente,
                args=(ip, porta, f"{self.nome} [{self.id}]: {mensagem}"),
                daemon=True
            ).start()

    # ------------------------------
    # Heartbeat (peer → coordenador)
    # ------------------------------
    # def enviar_heartbeat(self, coord_ip, coord_porta):
    #     while True:
    #         try:
    #             s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #             s.connect((coord_ip, coord_porta))
    #             msg = f"HEARTBEAT {self.ip} {self.porta}"
    #             s.send(msg.encode('utf-8'))
    #             s.close()
    #         except:
    #             print("[ERRO] Falha ao enviar heartbeat (coordenador inacessível).")
    #         time.sleep(5)

    # ------------------------------
    # Heartbeat do coordenador → peers
    # ------------------------------
    def enviar_heartbeat_coordenador(self):
        """O coordenador envia heartbeats periódicos para todos os peers."""
        while True:
            for ip, porta in list(self.peers):
                if (ip, porta) != (self.ip, self.porta):  # não envia para si mesmo
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect((ip, porta))
                        msg = f"HEARTBEAT {self.ip} {self.porta}"
                        s.send(msg.encode('utf-8'))
                        s.close()
                    except:
                        print(f"[ERRO] Coordenador não conseguiu enviar heartbeat a {ip}:{porta}")
            time.sleep(5)  # envia a cada 5 segundos

    # ------------------------------
    # Monitorar peers (coordenador)
    # ------------------------------
    # def monitorar_peers(self):
    #     while True:
    #         agora = time.time()
    #         for peer, ultimo in list(self.ultima_atividade.items()):
    #             if agora - ultimo > 15:
    #                 print(f"[SISTEMA] Peer inativo removido: {peer}")
    #                 if peer in self.peers:
    #                     self.peers.remove(peer)
    #         time.sleep(5)

    # ------------------------------
    # Monitora se o coordenador está ativo (para peers não coordenadores)
    # ------------------------------
    def monitorar_coordenador(self, coord_ip, coord_port):
        """Verifica se o coordenador ainda está enviando heartbeats."""
        print(f"[SISTEMA] Iniciando monitoramento do coordenador {coord_ip}:{coord_port}...")

        # Aguarda o primeiro heartbeat antes de iniciar o monitoramento
        while (coord_ip, coord_port) not in self.ultima_atividade:
            time.sleep(1)

        print(f"[SISTEMA] Primeiro heartbeat recebido do coordenador {coord_ip}:{coord_port}.")
        
        # Depois disso, começa o monitoramento regular
        while True:
            agora = time.time()
            ultimo_heartbeat = self.ultima_atividade.get((coord_ip, coord_port), 0)

            # Se passou mais de 15s desde o último heartbeat
            if agora - ultimo_heartbeat > 15:
                print(f"[ALERTA] Coordenador {coord_ip}:{coord_port} está inativo!")
                print("[SISTEMA] Este peer detectou a falha do coordenador.")
                break  # (poderia iniciar eleição aqui)
            
            time.sleep(5)

    # ------------------------------
    # Registro inicial e eleição
    # ------------------------------
    def iniciar_rede(self):
        if not self.peers:
            # Este peer é o coordenador
            self.coordenador = True
            self.id = 0
            self.mapa_ids[(self.ip, self.porta)] = self.id
            self.peers.append((self.ip, self.porta))
            print(f"[SISTEMA] {self.nome} é o coordenador da rede (ID 0).")

            # Inicia monitoramento
            Thread(target=self.enviar_heartbeat_coordenador, daemon=True).start()

        else:
            # Conecta ao coordenador
            coord_ip, coord_port = self.peers[0]
            msg = f"JOIN {self.ip} {self.porta}"
            self.cliente(coord_ip, coord_port, msg)
            print(f"[SISTEMA] Pedido de entrada enviado ao coordenador {coord_ip}:{coord_port}")

            # Inicia monitoramento do coordenador
            Thread(
                target=self.monitorar_coordenador,
                args=(coord_ip, coord_port),
                daemon=True
            ).start()

    # ------------------------------
    # Saída de um peer do chat
    # ------------------------------
    def sair_chat(self):
        msg = f"EXIT {self.ip} {self.porta}"

        # Envia para todos os peers conhecidos
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()

        # Caso o peer não seja o coordenador, também avisa o coordenador diretamente
        if not self.coordenador and self.peers:
            coord_ip, coord_port = self.peers[0]
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((coord_ip, coord_port))
                s.send(msg.encode('utf-8'))
                s.close()
                print(f"[SISTEMA] Coordenador {coord_ip}:{coord_port} notificado da saída.")
            except:
                print("[ERRO] Não foi possível notificar o coordenador da saída.")

    # ------------------------------
    # Interface do usuário
    # ------------------------------
    def iniciar(self):
        Thread(target=self.inicia_servidor, daemon=True).start()

        opcao = input("Deseja informar um peer coordenador existente? (s/n): ").strip().lower()
        if opcao == "s":
            ip = input("IP do coordenador: ")
            porta = int(input("Porta do coordenador: "))
            self.peers.append((ip, porta))

        self.iniciar_rede()

        print("\n[SISTEMA] Chat iniciado! Comandos disponíveis:")
        print(" - ADD <ip> <porta> : adiciona manualmente um peer")
        print(" - LIST             : lista peers conhecidos")
        print(" - EXIT             : encerra o chat")
        print("\nDigite suas mensagens abaixo:\n")

        while True:
            entrada = input("")

            if entrada.startswith("ADD "):
                try:
                    _, ip, porta = entrada.split()
                    porta = int(porta)
                    self.peers.append((ip, porta))
                    print(f"[SISTEMA] Peer adicionado: {ip}:{porta}")
                except:
                    print("[ERRO] Uso correto: ADD <ip> <porta>")

            elif entrada == "LIST":
                print("[SISTEMA] Peers conhecidos:")
                for ip, porta in self.peers:
                    print(f" - {ip}:{porta}")

            elif entrada == "EXIT":
                print("[SISTEMA] Saindo do chat...")
                self.sair_chat()
                break

            else:
                self.broadcast(entrada)


# ------------------------------
# Execução principal
# ------------------------------
def main():
    while True:
        try:
            entrada = input("Digite seu nome e porta local (<nome> <porta>): ")
            nome, porta = entrada.split()
            porta = int(porta)
            break
        except:
            print("[ERRO] Uso correto: <nome> <porta>")

    p = Peer(nome, "localhost", porta)
    p.iniciar()


if __name__ == "__main__":
    main()
