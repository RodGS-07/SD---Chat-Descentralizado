import socket
from threading import Thread

# Lista global de peers conectados
PEERS = []

def inicia_servidor(IP, PORTA, nome_usuario):
    """Servidor que recebe mensagens"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((IP, PORTA))
    server_socket.listen(5)

    print(f"[SERVIDOR] {nome_usuario} ouvindo em {IP}:{PORTA}")

    while True:
        client_socket, client_address = server_socket.accept()
        data = client_socket.recv(1024)
        decoded_data = data.decode('utf-8')
        print(f"\n> {decoded_data}")
        client_socket.close()


def cliente(IP, PORTA, nome_usuario, mensagem):
    """Cliente envia mensagem para um peer"""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((IP, PORTA))
        msg = f"{nome_usuario}: {mensagem}"
        client_socket.send(msg.encode('utf-8'))
    except:
        print(f"[ERRO] Não foi possível enviar mensagem para {IP}:{PORTA}")
    finally:
        client_socket.close()


def broadcast(mensagem, nome_usuario):
    """Envia a mensagem para todos os peers conhecidos"""
    for ip, porta in PEERS:
        Thread(target=cliente, args=(ip, porta, nome_usuario, mensagem), daemon=True).start()


def main():
    global PEERS

    IP_LOCAL = 'localhost'
    #PORTA_LOCAL = int(input("Digite sua porta local: "))
    #nome = input("Digite seu nome: ")
    while True:
        try:
            enter = input("Digite seu nome e sua porta local (<nome> <porta>): ")
            nome, PORTA_LOCAL = enter.split()
            PORTA_LOCAL = int(PORTA_LOCAL)
            break
        except:
            print("[ERRO] Uso correto: <nome> <porta>")

    # Inicia o servidor em paralelo
    Thread(target=inicia_servidor, args=(IP_LOCAL, PORTA_LOCAL, nome), daemon=True).start()

    print("\n[SISTEMA] Chat iniciado! Comandos disponíveis:")
    print(" - ADD <ip> <porta> : adiciona novo peer")
    print(" - REMOVE <ip> <porta> : remove peers da lista")
    print(" - LIST             : lista peers conectados")
    print(" - EXIT             : encerra o chat")
    print("\nDigite suas mensagens abaixo:\n")

    while True:
        entrada = input("")

        # Adiciona novos peers
        if entrada.startswith("ADD "):
            try:
                _, ip, porta = entrada.split()
                porta = int(porta)
                PEERS.append((ip, porta))
                print(f"[SISTEMA] Peer adicionado: {ip}:{porta}")
            except:
                print("[ERRO] Uso correto: ADD <ip> <porta>")

        # Remove um peer da lista
        elif entrada.startswith("REMOVE "):
            try:
                _, ip, porta = entrada.split()
                porta = int(porta)
                PEERS.remove((ip, porta))
                print(f"[SISTEMA] Peer adicionado: {ip}:{porta}")
            except:
                print("[ERRO] Uso correto: REMOVE <ip> <porta>")

        # Mostra lista de peers
        elif entrada == "LIST":
            if not PEERS:
                print("[SISTEMA] Nenhum peer conectado ainda.")
            else:
                print("[SISTEMA] Peers conhecidos:")
                for ip, porta in PEERS:
                    print(f" - {ip}:{porta}")

        # Encerra o chat
        elif entrada == "EXIT":
            print("[SISTEMA] Encerrando chat...")
            break

        # Envia mensagem para todos os peers
        else:
            broadcast(entrada, nome)


if __name__ == "__main__":
    main()
