Nome: Rodrigo Garcia da Silva
Matrícula: 202210032911

Link para o repositório no GitHub:
https://github.com/RodGS-07/SD---Chat-Descentralizado

Explicação do programa:
O programa é um chat que ocorre no terminal entre vários peers, usando o protocolo TCP para comunicação. Como o sistema possui uma arquitetura P2P, todos os peers estão conectados à mesma rede local (localhost) e cada peer possui uma porta própria, pois o sistema operacional não permite que mais de um peer possuam a mesma porta, se eles estiverem na mesma rede.
O código funciona, principalmente, a partir da classe Peer. Cada peer possui um nome, ID, IP e porta próprios, além de outros atributos importantes. A classe também possui métodos importantes para controlar a comunicação, a coordenação, o monitoramento de heartbeat e a eleição de um coordenador (algoritmo valentão).
Primeiramente, o usuário deve entrar com seu nome de usuário e porta, para que seja criado um Peer para ele. Em seguida, o usuário deve escolher se quer entrar em um chat já existente ou se quer criar o próprio chat. Se o usuário digitar 'n', um novo chat é criado, onde o peer passa a ser o coordenador. Se o usuário digitar 's', ele deve entrar com a porta do coordenador do chat que deseja entrar. Se o programa conseguir se conectar ao chat do coordenador desejado, o peer entra naquele chat; se o programa não conseguir se conectar ao chat, ele cria um novo chat para o peer, onde ele passa a ser o coordenador.
Assim, o usuário possui três opções ao entrar no chat:
- Mandar uma mensagem no chat, onde todos os peers conectados poderão ler a mensagem enviada;
- Digitar 'LIST', para listar, somente ao próprio peer, todos os peers que estão presentes naquele chat (mostrando nome, ID, IP e porta dos peers);
- Digitar 'EXIT', para sair do chat de forma voluntária; se ele for o coordenador, ele também notifica a saída aos outros peers para que eles iniciem a eleição do novo coordenador.
O coordenador é responsável por atribuir um ID único a cada peer, anunciar a entrada e a saída de um peer aos outros peers dentro de uma rede, e por enviar um heartbeat regularmente aos outros peers, para que eles saibam que o coordenador ainda está ativo.
O programa também possui alguns tratamentos de erros e tolerância a falhas, como, por exemplo, avisar ao usuário que uma porta não é válida (-5000, 5.5, 'oi', etc.) e alguns tratamentos de exceção causados por saída forçada pelo teclado (Ctrl+C).
Quando o coordenador apresentar uma falha e se desconecta do chat, um dos peers detecta a falha de heartbeat do coordenador, e avisa aos outros peers para iniciarem a eleição. A eleição é feita por meio do algoritmo valentão, no qual o peer com maior ID passa a ser o novo coordenador. Após a eleição, o novo coordenador é anunciado aos outros peers e ao próprio coordenador.

Bibliotecas Python usadas no código:
- socket: usada para comunicação entre processos usando o protocolo TCP
- time: usada para verificação de tempo decorrido e causar pausas leves em partes do código
- json: usado para serializar e desserializar dados importantes na memória, como lista de peers e mapas usados no código
- Thread: importado da biblioteca threading, usado para executar várias tarefas simultaneamente, sem bloquear o programa
- atexit: usada para rodar parte de um código, quando o programa for encerrado pelo usuário via 'EXIT'
- signal: usada para lidar com sinais do sistema operacional (neste caso, Ctrl+C)
- sys: usada para interagir com o sistema Python (neste caso, para encerrar o programa de modo controlado)