import socket

class Peer:
    def __init__(self, id, nickname, coordenador, IP, PORTA):
        self.id = id
        self.nickname = nickname
        self.coordenador = coordenador
        self.IP = IP
        self.PORTA = PORTA

    def inicia_servidor(self):
        # Cria um socket TCP/IP
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Liga o socket a um endereço e porta
        server_socket.bind((self.IP,self.PORTA))

        # Define o número máximo de conexões em fila
        server_socket.listen(5)

        print("Servidor pronto e aguardando conexões...")

        while True:
            # Aceita uma nova conexão
            client_socket, client_address = server_socket.accept()
            print(f"Conexão estabelecida com {client_address}")

            try:
                # Recebe dados do cliente
                data = client_socket.recv(1024)

                # Decodifica a mensagem recebida
                decoded_data = data.decode('utf-8')
                if decoded_data == 'exit' or decoded_data == 'sair':
                    print("Encerrando servidor...")
                    response = "Servidor encerrado"
                    client_socket.send(response.encode('utf-8'))
                    client_socket.close()
                    break
                else:
                    print(f"Recebido: {decoded_data}")

                # Envia uma resposta ao cliente
                response = "Mensagem recebida"
                client_socket.send(response.encode('utf-8'))

            except UnicodeDecodeError as e:
                print(f"Erro de decodificação: {e}")
                client_socket.send("Erro de decodificação".encode('utf-8'))

            finally:
                # Fecha a conexão
                client_socket.close()

    def conecta_servidor(self, IP, PORTA):
        # Cria um socket TCP
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            # Conecta ao servidor
            client_socket.connect((IP,PORTA))

            # Envia uma mensagem
            message = input("Digite uma mensagem: ")
            client_socket.send(message.encode('utf-8'))

            # Recebe a resposta do servidor
            response = client_socket.recv(1024)
            print(f"Resposta do servidor: {response.decode('utf-8')}")

        except ConnectionRefusedError as e:
            print(f"Erro de conexão: {e}")

        except UnicodeEncodeError as e:
            print(f"Erro de codificação: {e}")

        finally:
            # Fecha o socket
            client_socket.close()


def main():
    IP_SERVIDOR = 'localhost'
    PORTA_SERVIDOR = 65432
    p1 = Peer(1,"Rod",False,'localhost',65432)
    if p1.id == 1:
        p1.coordenador = True
        p1.IP = IP_SERVIDOR
        p1.PORTA = PORTA_SERVIDOR
    if p1.coordenador:
        p1.inicia_servidor()
    else:
        p1.conecta_servidor(IP_SERVIDOR,PORTA_SERVIDOR)
    
    
if __name__=="__main__":
    main()