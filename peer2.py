import socket
import time
import json
from threading import Thread

class Peer:
    def __init__(self, nome, ip, porta):
        self.nome = nome
        self.ip = ip
        self.porta = porta
        self.coordenador = False
        self.peers = []  # lista de (ip, porta)
        self.server_socket = None
        self.ultima_atividade = {}

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

            # Envia lista completa para o novo peer
            lista_serializada = json.dumps(self.peers)
            conn.send(lista_serializada.encode('utf-8'))

            # Notifica os outros peers sobre o novo
            self.notificar_peers(novo_peer)

        elif msg.startswith("UPDATE "):
            # Recebe atualização de lista do coordenador
            try:
                _, json_lista = msg.split(" ", 1)
                self.peers = json.loads(json_lista)
                print(f"[SISTEMA] Lista de peers atualizada ({len(self.peers)}):")
                for ip, porta in self.peers:
                    print(f" - {ip}:{porta}")
            except Exception as e:
                print(f"[ERRO UPDATE] {e}")
        elif msg.startswith("HEARTBEAT "):
            _, ip, porta = msg.split()
            porta = int(porta)
            self.ultima_atividade[(ip, porta)] = time.time()

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

            # Se for um JOIN, espera resposta com lista de peers
            if mensagem.startswith("JOIN "):
                resposta = client_socket.recv(2048).decode('utf-8')
                self.peers = json.loads(resposta)
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
        """Coordenador envia a lista atualizada para todos os peers"""
        lista_serializada = json.dumps(self.peers)
        msg = f"UPDATE {lista_serializada}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):  # não notifica a si mesmo
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()

    # ------------------------------
    # Broadcast (envia para todos)
    # ------------------------------
    def broadcast(self, mensagem):
        for ip, porta in self.peers:
            Thread(target=self.cliente, args=(ip, porta, f"{self.nome}: {mensagem}"), daemon=True).start()

    # ------------------------------
    # Heartbeat (indica que o peer ainda está ativo)
    # ------------------------------
    def enviar_heartbeat(self, coordenador_ip, coordenador_porta, meu_ip, minha_porta):
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((coordenador_ip, coordenador_porta))
                msg = f"HEARTBEAT {meu_ip} {minha_porta}"
                s.send(msg.encode('utf-8'))
                s.close()
            except:
                print("[ERRO] Falha ao enviar heartbeat.")
            time.sleep(5)  # envia a cada 5 segundos

    # ------------------------------
    # Monitora todos os peers da rede
    # ------------------------------
    def monitorar_peers(self):
        while True:
            agora = time.time()
            for peer, ultimo in list(self.ultima_atividade.items()):
                if agora - ultimo > 15:  # 15 segundos sem heartbeat
                    print(f"[SISTEMA] Peer inativo removido: {peer}")
                    self.peers.remove(peer)
            time.sleep(5)

    # ------------------------------
    # Registro inicial e eleição de coordenador
    # ------------------------------
    def iniciar_rede(self):
        if not self.peers:
            # Nenhum peer conhecido → este será o coordenador
            self.coordenador = True
            print(f"[SISTEMA] {self.nome} é o coordenador da rede.")
            self.peers.append((self.ip, self.porta))

             # Inicializa o dicionário de última atividade
            self.ultima_atividade = {}
            # Inicia thread de monitoramento
            Thread(target=self.monitorar_peers, daemon=True).start()
        else:
            # Registrar-se no coordenador
            coord_ip, coord_port = self.peers[0]
            msg = f"JOIN {self.ip} {self.porta}"
            self.cliente(coord_ip, coord_port, msg)
            print(f"[SISTEMA] Pedido de entrada enviado ao coordenador {coord_ip}:{coord_port}")

            # Inicia thread para enviar heartbeats ao coordenador
            Thread(
                target=self.enviar_heartbeat,
                args=(coord_ip, coord_port, self.ip, self.porta),
                daemon=True
            ).start()

    # ------------------------------
    # Interface de usuário
    # ------------------------------
    def iniciar(self):
        Thread(target=self.inicia_servidor, daemon=True).start()

        # Pergunta se o usuário quer adicionar peers conhecidos
        opcao = input("Deseja informar um peer coordenador existente? (s/n): ").strip().lower()
        if opcao == "s":
            ip = input("IP do coordenador: ")
            porta = int(input("Porta do coordenador: "))
            self.peers.append((ip, porta))

        self.iniciar_rede()

        print("\n[SISTEMA] Chat iniciado! Comandos disponíveis:")
        print(" - ADD <ip> <porta> : adiciona novo peer manualmente")
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
                    print(f"[SISTEMA] Peer adicionado manualmente: {ip}:{porta}")
                except:
                    print("[ERRO] Uso correto: ADD <ip> <porta>")

            elif entrada == "LIST":
                print("[SISTEMA] Peers conhecidos:")
                for ip, porta in self.peers:
                    print(f" - {ip}:{porta}")

            elif entrada == "EXIT":
                print("[SISTEMA] Encerrando chat...")
                break

            else:
                self.broadcast(entrada)


# ------------------------------
# Função principal
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
