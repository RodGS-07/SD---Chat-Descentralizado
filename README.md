Nome: Rodrigo Garcia da Silva
Matrícula: 202210032911

Link para o repositório no GitHub:
https://github.com/RodGS-07/SD---Chat-Descentralizado

Explicação do programa:
O programa é um chat que ocorre no terminal entre vários peers. Como o sistema possui uma arquitetura P2P, todos os peers estão conectados à mesma rede local (localhost) e cada peer possui uma porta própria.
O código funciona, principalmente, a partir da classe Peer. Cada peer possui um nome, ID, IP e porta próprios, além de outros atributos importantes. A classe também possui métodos importantes para controlar a comunicação, a coordenação, o monitoramento de heartbeat e a eleição de um coordenador (algoritmo valentão).
Primeiramente, o usuário deve entrar com seu nome de usuário e porta, para que seja criado um Peer para ele. Em seguida, o usuário deve escolher se quer entrar em um chat já existente ou se quer criar o próprio chat. Se o usuário digitar 'n', um novo chat é criado, onde o peer passa a ser o coordenador. Se o usuário digitar 's', ele deve entrar com a porta do coordenador do chat que deseja entrar. Se o programa conseguir se conectar ao chat do coordenador desejado, o peer entra naquele chat; se o programa não conseguir se conectar ao chat, ele cria um novo chat para o peer, onde ele passa a ser o coordenador.
Assim, o usuário possui três opções ao entrar no chat:
- Mandar uma mensagem no chat, onde todos os peers conectados poderão ler a mensagem enviada;
- Digitar 'LIST', para listar somente ao próprio peer, todos os peers que estão presentes naquele chat;
- Digitar 'EXIT', para sair do chat de forma voluntária; se ele for o coordenador, ele também notifica a saída aos outros peers para que eles iniciem a eleição do novo coordenador.