import socket
import time
import json
from threading import Thread
import atexit
import signal
import sys

# Constante usada para verificar se um peer digitou 'EXIT' para sair
EXITING = False

# =======================================================================
# Classe usada para representar e gerenciar peers, incluindo comunicação,
# coordenação, eleição e monitoramento por heartbeat
# =======================================================================
class Peer:
    # ============================================================
    # Construtor da classe Peer
    # ============================================================
    def __init__(self, nome, ip, porta):
        self.nome = nome  # nome de usuário do peer
        self.ip = ip  # endereço IP do peer (sempre 'localhost' neste programa)
        self.porta = porta  # porta do peer (cada peer deve ter uma porta diferente)
        self.id = None  # identificador único do peer dentro do chat atual (atribuído pelo coordenador)
        self.coordenador = False  # verifica se o próprio peer (self) é coordenador
        self.peers = []  # lista de (ip, porta)
        self.mapa_ids = {}  # mapeia (ip, porta) -> id
        self.mapa_nomes = {}  # mapeia (ip, porta) -> nome
        self.proximo_id = 1  # usado apenas pelo coordenador para atribuir IDs únicos a novos peers
        self.ultima_atividade = {}  # mapeia (ip, porta) -> momento (time.time()) da última atividade
        self.server_socket = None  # socket de servidor do peer
        self.coordenador_atual = None  # salva o coordenador atual de um chat
        self.em_eleicao = False  # verifica se o peer está em eleição no momento

    # ===========================================================================
    # Inicia o servidor, mantém ele ativo e escuta novas conexões de outros peers
    # ===========================================================================
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
    
    # =====================================================================================
    # Trata todas as mensagens recebidas — tanto mensagens de controle (JOIN, UPDATE, etc.)
    # quanto mensagens de chat enviadas pelos peers
    # =====================================================================================
    def tratar_mensagem(self, msg, conn):
        if msg.startswith("JOIN "):
            _, ip, porta, nome = msg.split()
            porta = int(porta)
            novo_peer = (ip, porta)

            if novo_peer not in self.peers:
                self.peers.append(novo_peer)
                
                aviso = f"[SISTEMA] Novo peer adicionado: {nome} ({ip}:{porta})"
                print(aviso)

                # Envia a mensagem para todos os outros peers
                for peer_ip, peer_porta in self.peers:
                    if (peer_ip, peer_porta) != (self.ip, self.porta) and (peer_ip, peer_porta) != (ip, porta):
                        Thread(target=self.cliente, args=(peer_ip, peer_porta, aviso), daemon=True).start()

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

        elif msg.startswith("HEARTBEAT "):
            _, ip, porta = msg.split()
            porta = int(porta)
            self.ultima_atividade[(ip, porta)] = time.time()
        
        elif msg.startswith("START_ELECTION"):
            Thread(target=self.iniciar_eleicao, daemon=True).start()

        elif msg.startswith("ELECTION "):
            self.tratar_eleicao(msg)

        elif msg.startswith("COORDINATOR "):
            self.tratar_novo_coordenador(msg)

        elif msg.startswith("REMOVE_COORDINATOR "):
            _, ip, porta = msg.split()
            porta = int(porta)
            coord = (ip, porta)
            if coord in self.peers:
                self.peers.remove(coord)
                nome_coord = self.mapa_nomes.get(coord, "Coordenador desconhecido")
                print(f"[SISTEMA] Coordenador {nome_coord} ({ip}:{porta}) removido da lista por inatividade.")

        elif msg.startswith("MAP_UPDATE "):
            _, json_dados = msg.split(" ", 1)
            try:
                dados = json.loads(json_dados)
                self.mapa_ids = {tuple(eval(k)): v for k, v in dados.get("ids", {}).items()}
                self.mapa_nomes = {tuple(eval(k)): v for k, v in dados.get("nomes", {}).items()}
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
            if msg.strip():  # só mostra se não for vazio
                print(f"\n> {msg}")

    # ========================================================================================
    # Envia mensagens para outros peers (tanto mensagens do chat quanto mensagens de controle)
    # ========================================================================================
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

    # ===============================================================================
    # Notifica todos os peers, enviando a lista de peers atualizada (mensagem UPDATE)
    # ===============================================================================
    def notificar_peers(self):
        lista_serializada = json.dumps(self.peers)
        msg = f"UPDATE {lista_serializada}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()

    # ==========================================================
    # Envia mapas de IDs e nomes para todos os peers
    # ==========================================================
    def enviar_mapas_para_peers(self):
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

    # ===========================================================================
    # ELEIÇÃO (BULLY) - Funções auxiliares para eleição usando algoritmo valentão
    # ===========================================================================
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
            self.coordenador = True
            self.coordenador_atual = (self.ip, self.porta)
            self.anunciar_coordenador()
            self.recalcular_ids()
            Thread(target=self.enviar_heartbeat_coordenador, daemon=True).start()

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
        print(f"[SISTEMA] IDs recalculados.")

    def tratar_eleicao(self, msg):
        _, id_origem = msg.split()
        id_origem = int(id_origem)
        if self.id > id_origem:
            Thread(target=self.iniciar_eleicao, daemon=True).start()

    def anunciar_coordenador(self):
        msg = f"COORDINATOR {self.ip} {self.porta} {self.nome}"
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip, self.porta):
                Thread(target=self.cliente, args=(ip, porta, msg), daemon=True).start()
        print(f"[ELEIÇÃO] Você ({self.ip}:{self.porta}) é o novo coordenador!")

    def tratar_novo_coordenador(self, msg):
        _, ip, porta, nome = msg.split()
        self.coordenador = False
        self.coordenador_atual = (ip, int(porta))
        self.em_eleicao = False
        print(f"[ELEIÇÃO] Novo coordenador eleito: {nome} ({ip}:{porta})")

    # ===============================================================================
    # HEARTBEAT - envia heartbeat aos outros peers, para indicar que ainda está ativo
    # ===============================================================================
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

    # =========================================================================
    # Monitora heartbeat do coordenador, para confirmar se ele ainda está ativo
    # =========================================================================
    def monitorar_coordenador(self):
        while True:
            if self.coordenador_atual:
                ultimo = self.ultima_atividade.get(self.coordenador_atual)
                if ultimo and time.time() - ultimo > 10:
                    print("[ALERTA] Coordenador inativo detectado!")
                    if self.coordenador_atual in self.peers:
                        provisorio = self.coordenador_atual
                        self.peers.remove(self.coordenador_atual)

                    # Avisa a todos os outros peers para removerem o coordenador
                    for peer_ip, peer_porta in list(self.peers):
                        if (peer_ip, peer_porta) != (self.ip, self.porta):
                            try:
                                msg = f"REMOVE_COORDINATOR {provisorio[0]} {provisorio[1]}"
                                Thread(target=self.cliente, args=(peer_ip, peer_porta, msg), daemon=True).start()
                            except Exception:
                                pass

                    # Inicia a eleição localmente
                    Thread(target=self.iniciar_eleicao, daemon=True).start()
                    # Para evitar múltiplos disparos
                    time.sleep(5)
            time.sleep(2)

    # ===================================================================
    # Inicia rede para um peer, permitindo que inicie ou entre em um chat
    # ===================================================================
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
    # Inicia a conexão de um peer com um chat
    # ============================================================
    def iniciar(self):
        global EXITING
        Thread(target=self.inicia_servidor, daemon=True).start()
        time.sleep(1)

        opcao = input("Deseja informar um coordenador existente? (s/n): ").strip().lower()
        while opcao.lower() != "s" and opcao.lower() != "n":
            print("[ERRO] Somente 's' e 'n' são opções válidas. Digite apenas 's' ou 'n'. ")
            opcao = input("Deseja informar um coordenador existente? (s/n): ").strip().lower()

        if opcao == "s":
            while True:
                try:
                    porta_str = input("Porta do coordenador: ").strip()

                    # Verifica se a entrada é válida
                    if '.' in porta_str or not porta_str.isdigit():
                        print("[ERRO] A porta deve ser um número inteiro entre 0 e 65535.")
                        continue

                    porta = int(porta_str)
                    if not (0 <= porta <= 65535):
                        print("[ERRO] A porta deve estar entre 0 e 65535.")
                        continue

                    # Verifica se há alguém ouvindo nessa porta
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    resultado = s.connect_ex(('localhost', porta))
                    s.close()

                    if resultado == 0:
                        # Conexão bem-sucedida -> coordenador existente
                        print(f"[SISTEMA] Coordenador encontrado em localhost:{porta}.")
                        time.sleep(1)
                        self.peers.append(('localhost', porta))
                    else:
                        # Ninguém ouvindo -> cria rede própria
                        print(f"[SISTEMA] Nenhum coordenador encontrado na porta {porta}. Criando rede própria para {self.nome}...")
                    break

                except ValueError:
                    print("[ERRO] Entrada inválida. A porta deve ser um número inteiro.")
                except Exception as e:
                    print(f"[ERRO] {e}")
        else:
            print(f"[SISTEMA] Criando rede própria para {self.nome}...")
            time.sleep(1)

        self.iniciar_rede()

        time.sleep(1)
        if self.coordenador:
            print("\n[SISTEMA] Chat iniciado!\nDigite 'LIST' para ver peers (nome, ID, IP e porta) ou 'EXIT' para sair.\n")
        else:
            print("\n[SISTEMA] Boas vindas ao chat!\nDigite 'LIST' para ver peers (nome, ID, IP e porta) ou 'EXIT' para sair.\n")

        # Palavras reservadas que não devem ser enviadas
        comandos_reservados = {
            "JOIN", "UPDATE", "ELECTION", "COORDINATOR", "HEARTBEAT",
            "EXIT", "MAP_UPDATE", "REMOVE_COORDINATOR", "START_ELECTION"
        }

        while True:
            try:
                entrada = input("")
                if entrada == "EXIT":
                    EXITING = True
                    break
                elif entrada == "LIST":
                    for peer in self.peers:
                        nome = self.mapa_nomes.get(peer, "Desconhecido")
                        id = self.mapa_ids.get(peer, None)
                        print(f"{nome} [{id}] -> {peer}")
                elif entrada.strip():
                    primeira_palavra = entrada.strip().split()[0].upper()
                    if primeira_palavra in comandos_reservados:
                        print(f"[ERRO] '{primeira_palavra}' é uma palavra reservada do sistema. Use outro texto.")
                        continue
                    self.enviar_mensagem(entrada)
            except KeyboardInterrupt:
                self.encerrar()

    # ============================================================
    # Envia mensagens, permitidas pelo sistema, para o chat
    # ============================================================
    def enviar_mensagem(self, mensagem):
        for ip, porta in self.peers:
            if (ip, porta) != (self.ip,self.porta):
                Thread(target=self.cliente,
                    args=(ip, porta, f"{self.nome} [{self.id}]: {mensagem}"),
                    daemon=True).start()
            else:
                Thread(target=self.cliente,
                    args=(ip, porta, f"Você [{self.id}]: {mensagem}"),
                    daemon=True).start()

    # ========================================================================
    # Encerra conexão do peer com a rede, saindo do chat e encerrando programa
    # ========================================================================
    def encerrar(self, via_exit=False):
        print(f"\n[SISTEMA] {self.nome} encerrando...")
        msg = f"EXIT {self.ip} {self.porta} {self.nome}"

        # Coordenador não anuncia sua própria saída
        if self.coordenador:
            if not via_exit:
                print("[SISTEMA] Coordenador encerrando — saída será detectada por falha de heartbeat.")
                sys.exit(0)
            else:
                print("[SISTEMA] Coordenador saindo voluntariamente — escolhendo sucessor...")

                # Remove-se das estruturas locais (não será mais candidato)
                if (self.ip, self.porta) in self.peers:
                    try:
                        self.peers.remove((self.ip, self.porta))
                    except ValueError:
                        pass
                self.mapa_ids.pop((self.ip, self.porta), None)
                self.mapa_nomes.pop((self.ip, self.porta), None)

                # Notifica todos os peers com a lista atualizada e o mapa atualizado
                # (assim todos sabem que o coordenador saiu e não o considerarão candidato)
                self.notificar_peers(None)            # envia UPDATE com nova self.peers
                self.enviar_mapas_para_peers()        # envia MAP_UPDATE com mapa sem o antigo coordenador

                # Pede explicitamente que os outros iniciem eleição
                for ip, porta in list(self.peers):
                    if (ip, porta) != (self.ip, self.porta):
                        try:
                            Thread(target=self.cliente, args=(ip, porta, "START_ELECTION"), daemon=True).start()
                        except:
                            pass

                # Marca que não é mais coordenador e sai
                self.coordenador = False
                self.em_eleicao = False

                # Dá um pequeno tempo para pedidos serem enviados
                time.sleep(0.5)

                # Não continua participando da eleição localmente (já saiu)
                # e retorna para encerrar normalmente (não envia EXIT pois já fez UPDATE)
                print("[SISTEMA] Transferência solicitada — finalizando processo do coordenador.")
                return

        for ip, porta in list(self.peers):
            if (ip, porta) != (self.ip, self.porta):
                try:
                    self.cliente(ip, porta, msg)
                except:
                    pass
        print("[SISTEMA] Mensagem de saída enviada.")
        if not via_exit:
            sys.exit(0)

# ============================================================
# Verifica disponibilidade e validação da porta
# ============================================================
def porta_disponivel(porta):
    """Verifica se a porta é válida e está livre para uso."""
    # Verifica tipo e faixa numérica
    if not isinstance(porta, int):
        print("[ERRO] A porta deve ser um número inteiro.")
        return False
    if not (0 <= porta <= 65535):
        print("[ERRO] A porta deve estar entre 0 e 65535.")
        return False

    # Tenta fazer o bind (se der erro, já está em uso)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", porta))
            return True
        except OSError:
            print(f"[ERRO] A porta {porta} já está sendo usada por outro processo.")
            return False

# ============================================================
# Função main
# ============================================================
def main():
    global EXITING
    EXITING = False
    while True:
        try:
            entrada = input("Digite seu nome e porta local (<nome> <porta>): ")
            nome, porta_str = entrada.split()

            # Detecta valores não inteiros (float, texto, etc.)
            if '.' in porta_str or not porta_str.isdigit():
                print("[ERRO] A porta deve ser um número inteiro entre 0 e 65535.")
                continue

            porta = int(porta_str)

            # Verifica validade e disponibilidade
            if porta_disponivel(porta):
                break
        except ValueError:
            print("[ERRO] Entrada inválida. Use o formato: <nome> <porta>")
        except Exception as e:
            print(f"[ERRO] {e}")

    p = Peer(nome, "localhost", porta)

    def sair_falha(*args):
        p.encerrar(via_exit=False)
        sys.exit(0)

    def sair_exit():
        p.encerrar(via_exit=True)

    p.iniciar()

    if not EXITING:
        signal.signal(signal.SIGINT, sair_falha)
    else:
        atexit.register(sair_exit)

if __name__ == "__main__":
    main()
