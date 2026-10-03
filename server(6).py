"""
server.py - Servidor do jogo Risk via Pyro5 (RMI em Python)

Como executar:
  1. Inicie o servidor de nomes: python -m Pyro5.nameserver
  2. Inicie o servidor do jogo:  python server.py
"""

import Pyro5.api
import Pyro5.server
import random
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from game_data import (
    CONTINENTES, ADJACENCIAS, TODOS_OS_TERRITORIOS,
    TIPOS_DE_CARTA, BONUS_TROCA_CARTAS
)


@Pyro5.api.expose
class JogoRisk:
    """
    Objeto remoto que expoe todos os metodos do jogo.
    Cada chamada de cliente chega aqui via RMI (Pyro5).
    """

    def __init__(self):
        self._trava = threading.Lock()

        # Jogadores: {"1": {"nome": str, "tropas_para_colocar": int, "cartas": []}}
        self._jogadores: dict = {}

        # Territorios: {nome: {"dono": "1"|"2"|None, "tropas": int}}
        self._territorios: dict = {}

        # Estado geral da partida
        self._jogador_atual:  str | None = None
        self._fase:           str        = "aguardando"  # aguardando | posicionamento | batalha | encerrado
        self._vencedor:       str | None = None
        self._registro:       list[str]  = []

        # Controle de acoes especiais do turno atual
        self._jogador_moveu_tropas_neste_turno:      bool = False
        self._jogador_conquistou_territorio_neste_turno: bool = False

        self._inicializar_territorios()

    # -------------------------------------------------------------------------
    # Metodos de inicializacao (privados)
    # -------------------------------------------------------------------------

    def _inicializar_territorios(self):
        """Cria todos os territorios sem dono e sem tropas."""
        for territorio in TODOS_OS_TERRITORIOS:
            self._territorios[territorio] = {"dono": None, "tropas": 0}

    def _registrar(self, mensagem: str):
        """Adiciona mensagem ao historico de acoes. Mantem no maximo 30 entradas."""
        self._registro.append(mensagem)
        if len(self._registro) > 30:
            self._registro.pop(0)
        print(f"[REGISTRO] {mensagem}")

    # -------------------------------------------------------------------------
    # Metodos publicos - acessiveis pelos clientes via RMI
    # -------------------------------------------------------------------------

    def entrar_no_jogo(self, nome_jogador: str) -> dict:
        """
        Registra um jogador na partida.
        Retorna: {"sucesso": bool, "id_jogador": "1"|"2", "mensagem": str}
        Quando o segundo jogador entra, a partida inicia automaticamente.
        """
        with self._trava:
            if len(self._jogadores) >= 2:
                return {"sucesso": False, "mensagem": "Jogo cheio (maximo 2 jogadores)."}
            if self._fase != "aguardando":
                return {"sucesso": False, "mensagem": "Partida ja iniciada."}

            id_jogador = str(len(self._jogadores) + 1)
            self._jogadores[id_jogador] = {
                "nome":               nome_jogador,
                "tropas_para_colocar": 0,
                "cartas":             []
            }
            self._registrar(f"[ENTRADA] {nome_jogador} entrou como Jogador {id_jogador}")

            if len(self._jogadores) == 2:
                self._distribuir_territorios_e_iniciar()

            return {
                "sucesso":    True,
                "id_jogador": id_jogador,
                "mensagem":   f"Bem-vindo, {nome_jogador}! Voce e o Jogador {id_jogador}."
            }

    def obter_estado_do_jogo(self, id_jogador_solicitante: str = None) -> dict:
        """
        Retorna o estado completo da partida para o cliente.
        - Cartas do proprio jogador: retorna a lista completa.
        - Cartas do oponente: retorna apenas a quantidade (privacidade).
        """
        with self._trava:
            visao_jogadores = {}
            for pid, dados in self._jogadores.items():
                copia = dict(dados)
                if pid != id_jogador_solicitante:
                    copia["cartas"]           = []
                    copia["quantidade_cartas"] = len(dados["cartas"])
                else:
                    copia["quantidade_cartas"] = len(dados["cartas"])
                visao_jogadores[pid] = copia

            return {
                "fase":                    self._fase,
                "jogador_atual":           self._jogador_atual,
                "jogadores":               visao_jogadores,
                "territorios":             dict(self._territorios),
                "vencedor":                self._vencedor,
                "registro":                list(self._registro),
                "jogador_moveu_tropas":    self._jogador_moveu_tropas_neste_turno,
            }

    def colocar_tropas(self, id_jogador: str, territorio: str, quantidade: int = 1) -> dict:
        """
        Coloca tropas em um territorio proprio.
        Usado tanto na fase de posicionamento inicial quanto na de reforco do turno.
        Retorna: {"sucesso": bool, "mensagem": str (se erro)}
        """
        with self._trava:
            ok, msg = self._verificar_vez_e_fase(id_jogador, ("posicionamento", "batalha"))
            if not ok:
                return {"sucesso": False, "mensagem": msg}

            if territorio not in self._territorios:
                return {"sucesso": False, "mensagem": f"Territorio '{territorio}' invalido."}
            if self._territorios[territorio]["dono"] != id_jogador:
                return {"sucesso": False, "mensagem": "Este territorio nao e seu."}

            disponiveis = self._jogadores[id_jogador]["tropas_para_colocar"]
            if quantidade < 1 or quantidade > disponiveis:
                return {"sucesso": False, "mensagem": f"Voce tem apenas {disponiveis} tropa(s) disponivel(is)."}

            self._territorios[territorio]["tropas"] += quantidade
            self._jogadores[id_jogador]["tropas_para_colocar"] -= quantidade
            self._registrar(
                f"[REFORCO] Jogador {id_jogador} colocou {quantidade} tropa(s) em "
                f"{territorio} ({self._territorios[territorio]['tropas']} total)"
            )

            # Verificar se o posicionamento inicial foi concluido
            if self._fase == "posicionamento" and self._jogadores[id_jogador]["tropas_para_colocar"] == 0:
                outro = "2" if id_jogador == "1" else "1"
                if self._jogadores[outro]["tropas_para_colocar"] > 0:
                    self._jogador_atual = outro
                    self._registrar(f"[VEZ] Jogador {outro} ({self._jogadores[outro]['nome']}) deve posicionar.")
                else:
                    self._iniciar_fase_de_batalha()

            return {"sucesso": True}

    def trocar_cartas_por_tropas(self, id_jogador: str, indices_cartas: list) -> dict:
        """
        Troca 3 cartas por tropas extras antes de distribuir reforcos.
        Combinacoes validas: 3 iguais  ou  1 de cada tipo (3 diferentes).
        Indices duplicados sao rejeitados.
        Retorna: {"sucesso": bool, "bonus": int, "escolhidas": list, "mensagem": str (se erro)}
        """
        with self._trava:
            ok, msg = self._verificar_vez_e_fase(id_jogador, ("batalha",))
            if not ok:
                return {"sucesso": False, "mensagem": msg}

            cartas = self._jogadores[id_jogador]["cartas"]

            if len(indices_cartas) != 3:
                return {"sucesso": False, "mensagem": "Selecione exatamente 3 cartas."}

            if len(set(indices_cartas)) != 3:
                return {"sucesso": False, "mensagem": "Selecione 3 cartas diferentes (sem repetir indice)."}

            if any(i < 0 or i >= len(cartas) for i in indices_cartas):
                return {"sucesso": False, "mensagem": "Indice de carta invalido."}

            escolhidas   = [cartas[i] for i in indices_cartas]
            tipos_unicos = set(escolhidas)

            # 3 iguais -> len==1 | 1 de cada tipo -> len==3
            if len(tipos_unicos) not in (1, 3):
                return {"sucesso": False, "mensagem": "Combinacao invalida. Use 3 iguais ou 1 de cada tipo."}

            # Remove de tras para frente para nao deslocar os indices restantes
            for i in sorted(indices_cartas, reverse=True):
                cartas.pop(i)

            self._jogadores[id_jogador]["tropas_para_colocar"] += BONUS_TROCA_CARTAS
            self._registrar(f"[CARTAS] Jogador {id_jogador} trocou cartas e ganhou +{BONUS_TROCA_CARTAS} tropas.")
            return {"sucesso": True, "bonus": BONUS_TROCA_CARTAS, "escolhidas": escolhidas}

    def atacar_territorio(self, id_jogador: str, territorio_origem: str,
                          territorio_alvo: str, quantidade_dados_ataque: int) -> dict:
        """
        Realiza um ataque de um territorio proprio para um territorio inimigo adjacente.
        Regras dos dados: atacante rola ate 3, defensor rola ate 2.
        Em caso de empate no par, o defensor vence.
        Retorna: {sucesso, dados_ataque, dados_defesa, baixas_ataque, baixas_defesa, conquistado, vencedor}
        """
        with self._trava:
            ok, msg = self._verificar_vez_e_fase(id_jogador, ("batalha",))
            if not ok:
                return {"sucesso": False, "mensagem": msg}

            if self._jogadores[id_jogador]["tropas_para_colocar"] > 0:
                return {"sucesso": False, "mensagem": "Distribua todos os reforcos antes de atacar."}

            erro = self._verificar_ataque_valido(id_jogador, territorio_origem, territorio_alvo)
            if erro:
                return {"sucesso": False, "mensagem": erro}

            origem = self._territorios[territorio_origem]
            alvo   = self._territorios[territorio_alvo]

            # Calcular numero de dados de cada lado
            max_dados_ataque    = min(3, origem["tropas"] - 1)
            quantidade_dados_ataque = max(1, min(quantidade_dados_ataque, max_dados_ataque))
            quantidade_dados_defesa = min(2, alvo["tropas"])

            # Rolar e ordenar dados do maior para o menor
            dados_ataque  = sorted([random.randint(1, 6) for _ in range(quantidade_dados_ataque)],  reverse=True)
            dados_defesa  = sorted([random.randint(1, 6) for _ in range(quantidade_dados_defesa)], reverse=True)

            # Comparar par a par: empate favorece o defensor
            baixas_ataque  = 0
            baixas_defesa  = 0
            for atk, def_ in zip(dados_ataque, dados_defesa):
                if atk > def_:
                    baixas_defesa += 1
                else:
                    baixas_ataque += 1

            origem["tropas"] -= baixas_ataque
            alvo["tropas"]   -= baixas_defesa

            conquistado = False
            if alvo["tropas"] <= 0:
                tropas_movidas   = quantidade_dados_ataque - baixas_ataque
                alvo["dono"]     = id_jogador
                alvo["tropas"]   = tropas_movidas
                origem["tropas"] -= tropas_movidas
                conquistado       = True
                self._jogador_conquistou_territorio_neste_turno = True
                self._registrar(f"[CONQUISTA] Jogador {id_jogador} conquistou {territorio_alvo}.")

                if all(v["dono"] == id_jogador for v in self._territorios.values()):
                    self._vencedor = id_jogador
                    self._fase     = "encerrado"
                    self._registrar(f"[VITORIA] Jogador {id_jogador} ({self._jogadores[id_jogador]['nome']}) venceu!")

            self._registrar(
                f"[ATAQUE] {territorio_origem} -> {territorio_alvo} | "
                f"Ataque: {dados_ataque}  Defesa: {dados_defesa} | "
                f"Baixas: -{baixas_ataque} atacante  -{baixas_defesa} defensor"
            )

            return {
                "sucesso":        True,
                "dados_ataque":   dados_ataque,
                "dados_defesa":   dados_defesa,
                "baixas_ataque":  baixas_ataque,
                "baixas_defesa":  baixas_defesa,
                "conquistado":    conquistado,
                "vencedor":       self._vencedor,
            }

    def mover_tropas_entre_territorios(self, id_jogador: str, territorio_origem: str,
                                       territorio_destino: str, quantidade: int) -> dict:
        """
        Movimentacao (Fortificacao): transfere tropas entre dois territorios
        proprios e adjacentes. Permitido uma unica vez por turno, apos os ataques.
        Retorna: {"sucesso": bool, "mensagem": str (se erro)}
        """
        with self._trava:
            ok, msg = self._verificar_vez_e_fase(id_jogador, ("batalha",))
            if not ok:
                return {"sucesso": False, "mensagem": msg}

            if self._jogadores[id_jogador]["tropas_para_colocar"] > 0:
                return {"sucesso": False, "mensagem": "Distribua os reforcos antes de mover tropas."}

            if self._jogador_moveu_tropas_neste_turno:
                return {"sucesso": False, "mensagem": "Voce ja moveu tropas neste turno."}

            if territorio_origem not in self._territorios:
                return {"sucesso": False, "mensagem": "Territorio de origem invalido."}
            if territorio_destino not in self._territorios:
                return {"sucesso": False, "mensagem": "Territorio de destino invalido."}

            origem  = self._territorios[territorio_origem]
            destino = self._territorios[territorio_destino]

            if origem["dono"] != id_jogador:
                return {"sucesso": False, "mensagem": "O territorio de origem nao e seu."}
            if destino["dono"] != id_jogador:
                return {"sucesso": False, "mensagem": "O territorio de destino nao e seu."}
            if territorio_destino not in ADJACENCIAS.get(territorio_origem, []):
                return {"sucesso": False, "mensagem": f"{territorio_origem} e {territorio_destino} nao sao adjacentes."}
            if origem["tropas"] < 2:
                return {"sucesso": False, "mensagem": "Precisa de pelo menos 2 tropas na origem para mover."}
            if quantidade < 1 or quantidade > origem["tropas"] - 1:
                return {"sucesso": False, "mensagem": f"Pode mover de 1 a {origem['tropas'] - 1} tropa(s)."}

            origem["tropas"]  -= quantidade
            destino["tropas"] += quantidade
            self._jogador_moveu_tropas_neste_turno = True

            self._registrar(
                f"[MOVIMENTACAO] Jogador {id_jogador} transferiu {quantidade} tropa(s): "
                f"{territorio_origem} ({origem['tropas']}) -> {territorio_destino} ({destino['tropas']})"
            )
            return {"sucesso": True}

    def encerrar_turno(self, id_jogador: str) -> dict:
        """
        Encerra o turno do jogador atual.
        - Se conquistou territorio neste turno, recebe uma carta aleatoria.
        - Passa a vez para o proximo jogador.
        - Calcula e atribui os reforcos do proximo jogador.
        Retorna: {"sucesso": bool, "carta_recebida": str|None, "mensagem": str (se erro)}
        """
        with self._trava:
            ok, msg = self._verificar_vez_e_fase(id_jogador, ("batalha",))
            if not ok:
                return {"sucesso": False, "mensagem": msg}

            if self._jogadores[id_jogador]["tropas_para_colocar"] > 0:
                return {"sucesso": False, "mensagem": "Distribua todos os reforcos antes de encerrar o turno."}

            # Dar carta se conquistou pelo menos 1 territorio neste turno
            carta_recebida = None
            if self._jogador_conquistou_territorio_neste_turno:
                carta_recebida = random.choice(TIPOS_DE_CARTA)
                self._jogadores[id_jogador]["cartas"].append(carta_recebida)
                self._registrar(f"[CARTA] Jogador {id_jogador} recebeu uma carta (mantida em segredo).")

            # Passar a vez e resetar os controles do turno
            proximo_jogador = "2" if id_jogador == "1" else "1"
            self._jogador_atual                              = proximo_jogador
            self._jogador_moveu_tropas_neste_turno           = False
            self._jogador_conquistou_territorio_neste_turno  = False

            self._calcular_e_distribuir_reforcos(proximo_jogador)
            self._registrar(f"[VEZ] Vez do Jogador {proximo_jogador} ({self._jogadores[proximo_jogador]['nome']})")
            return {"sucesso": True, "carta_recebida": carta_recebida}

    # -------------------------------------------------------------------------
    # Metodos de logica interna (privados)
    # -------------------------------------------------------------------------

    def _distribuir_territorios_e_iniciar(self):
        """Embaralha e divide os territorios entre os jogadores. Inicia o posicionamento."""
        embaralhados = TODOS_OS_TERRITORIOS.copy()
        random.shuffle(embaralhados)
        metade = len(embaralhados) // 2

        for i, territorio in enumerate(embaralhados):
            dono = "1" if i < metade else "2"
            self._territorios[territorio] = {"dono": dono, "tropas": 1}

        for pid in ["1", "2"]:
            self._jogadores[pid]["tropas_para_colocar"] = 8

        self._jogador_atual                              = "1"
        self._fase                                       = "posicionamento"
        self._jogador_moveu_tropas_neste_turno           = False
        self._jogador_conquistou_territorio_neste_turno  = False

        self._registrar("-" * 50)
        self._registrar("[INICIO] Partida iniciada. Territorios distribuidos aleatoriamente.")
        self._registrar("[POSICIONAMENTO] Cada jogador coloca 8 tropas extras.")
        self._registrar(f"[VEZ] Comeca Jogador 1 ({self._jogadores['1']['nome']}).")

    def _iniciar_fase_de_batalha(self):
        """Transita para a fase de batalha apos o posicionamento inicial."""
        self._fase                                       = "batalha"
        self._jogador_atual                              = "1"
        self._jogador_moveu_tropas_neste_turno           = False
        self._jogador_conquistou_territorio_neste_turno  = False

        self._registrar("-" * 50)
        self._registrar("[BATALHA] Fase de batalha iniciada!")
        self._calcular_e_distribuir_reforcos("1")
        self._registrar(f"[VEZ] Vez do Jogador 1 ({self._jogadores['1']['nome']})")

    def _calcular_e_distribuir_reforcos(self, id_jogador: str):
        """
        Calcula e atribui os reforcos do inicio do turno.
        Base: max(3, territorios_do_jogador / 3).
        Bonus: soma os bonus dos continentes totalmente controlados.
        """
        territorios_do_jogador = [
            t for t, v in self._territorios.items() if v["dono"] == id_jogador
        ]
        reforcos_base = max(3, len(territorios_do_jogador) // 3)

        bonus_continente = 0
        for nome_continente, dados_continente in CONTINENTES.items():
            todos_controlados = all(
                self._territorios[t]["dono"] == id_jogador
                for t in dados_continente["territorios"]
            )
            if todos_controlados:
                bonus_continente += dados_continente["bonus"]
                self._registrar(
                    f"[BONUS] Jogador {id_jogador} controla {nome_continente}. "
                    f"Bonus: +{dados_continente['bonus']}"
                )

        total = reforcos_base + bonus_continente
        self._jogadores[id_jogador]["tropas_para_colocar"] = total
        self._registrar(
            f"[REFORCOS] Jogador {id_jogador} recebe {total} tropa(s) "
            f"(base: {reforcos_base} + continentes: {bonus_continente})"
        )

    def _verificar_vez_e_fase(self, id_jogador: str, fases_permitidas: tuple) -> tuple[bool, str]:
        """
        Verifica se e a vez do jogador e se a fase atual e permitida.
        Chamado no inicio de todo metodo de acao.
        """
        if self._fase not in fases_permitidas:
            return False, f"Fase incorreta (atual: {self._fase})."
        if self._jogador_atual != id_jogador:
            return False, "Nao e sua vez."
        return True, ""

    def _verificar_ataque_valido(self, id_jogador: str, origem: str, alvo: str) -> str | None:
        """
        Valida as 4 regras geograficas de um ataque.
        Retorna mensagem de erro ou None se tudo estiver correto.
        """
        if origem not in self._territorios:
            return f"Territorio de origem '{origem}' nao existe."
        if alvo not in self._territorios:
            return f"Territorio alvo '{alvo}' nao existe."
        if self._territorios[origem]["dono"] != id_jogador:
            return "Voce nao controla o territorio de origem."
        if self._territorios[alvo]["dono"] == id_jogador:
            return "Nao pode atacar seu proprio territorio."
        if alvo not in ADJACENCIAS.get(origem, []):
            return f"'{origem}' e '{alvo}' nao sao adjacentes."
        if self._territorios[origem]["tropas"] < 2:
            return "Precisa de pelo menos 2 tropas no territorio para atacar."
        return None


# -------------------------------------------------------------------------
# Inicializacao do servidor
# -------------------------------------------------------------------------

def main():
    print("Servidor do Risk - Pyro5 / RMI")
    print("-" * 35)

    try:
        demon  = Pyro5.server.Daemon()
        servidor_nomes = Pyro5.api.locate_ns()
    except Exception as e:
        print(f"[ERRO] Servidor de nomes nao encontrado: {e}")
        print("Execute primeiro: python -m Pyro5.nameserver")
        sys.exit(1)

    jogo = JogoRisk()
    uri  = demon.register(jogo, "risk.jogo")
    servidor_nomes.register("risk.jogo", uri)

    print(f"Objeto registrado: PYRONAME:risk.jogo")
    print(f"URI: {uri}\n")
    print("Aguardando jogadores... (Ctrl+C para parar)")

    demon.requestLoop()


if __name__ == "__main__":
    main()
