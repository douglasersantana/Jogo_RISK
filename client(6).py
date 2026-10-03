"""
Cliente do jogo Risk via Pyro5

python client.py
"""

import Pyro5.api                
import time
import os               
import sys                                       
from collections import Counter             

sys.path.insert(0, os.path.dirname(__file__))     # Permite importar game_data.py do mesmo diretorio
from game_data import CONTINENTES, ADJACENCIAS



# Funcoes auxiliares de terminal


def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")   


def perguntar(prompt: str = "") -> str:                
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)


def escolher_territorio_da_lista(rotulo: str, opcoes: list) -> str | None:
    """Exibe lista numerada de territorios e retorna o escolhido."""
    print(f"\n  {rotulo}:")
    for i, t in enumerate(opcoes, 1):
        print(f"    {i:2}. {t}")
    escolha = perguntar("  Numero (ou 'v' para voltar): ")
    if escolha.lower() == "v":
        return None
    try:
        idx = int(escolha) - 1
        if 0 <= idx < len(opcoes):
            return opcoes[idx]
    except ValueError:
        pass
    return next((t for t in opcoes if t.lower() == escolha.lower()), None)


def escolher_numero(prompt: str, minimo: int, maximo: int) -> int | None:       
    """Pede um numero inteiro dentro do intervalo dado."""
    valor = perguntar(prompt)
    try:
        n = int(valor)
        if minimo <= n <= maximo:
            return n
    except ValueError:
        pass
    print(f"  Valor invalido. Digite um numero entre {minimo} e {maximo}.")
    return None



# Exibicao do estado do jogo


def exibir_estado_do_jogo(estado: dict, meu_id: str):
    """Limpa a tela e redesenha o estado completo: jogadores, mapa e registro."""
    limpar_tela()
    territorios     = estado["territorios"]
    jogadores       = estado["jogadores"]
    jogador_atual   = estado["jogador_atual"]
    fase            = estado["fase"]
    jogador_moveu   = estado.get("jogador_moveu_tropas", False)

    NOMES_DAS_FASES = {
        "aguardando":    "Aguardando jogadores",
        "posicionamento": "Posicionamento inicial",
        "batalha":       "Batalha",
        "encerrado":     "Fim de jogo",
    }

    print("=" * 66)
    print("           R I S K  -  Jogo Simplificado (Pyro5 / RMI)")
    print("=" * 66)
    print(f"  Fase: {NOMES_DAS_FASES.get(fase, fase)}   |   Turno: Jogador {jogador_atual}")
    print()

    # Painel de jogadores
    print("  JOGADORES:")
    for pid, dados in jogadores.items():
        rotulo        = "VOCE" if pid == meu_id else f"J{pid}"
        tag_vez       = " [SUA VEZ]"    if pid == jogador_atual == meu_id else \
                        " [VEZ DELES]"  if pid == jogador_atual else ""
        territorios_proprios = sum(1 for t in territorios.values() if t["dono"] == pid)
        total_tropas  = sum(t["tropas"] for t in territorios.values() if t["dono"] == pid)
        reforcos      = dados["tropas_para_colocar"]
        tag_moveu     = " [movimentacao usada]" if pid == jogador_atual == meu_id and jogador_moveu else ""

        print(f"  [{rotulo}] Jogador {pid} - {dados['nome']}{tag_vez}")
        print(f"       Territorios: {territorios_proprios}/{len(territorios)}   "
              f"Exercitos: {total_tropas}   "
              f"Reforcos disponiveis: {reforcos}{tag_moveu}")

        # Cartas: proprias mostram detalhes, oponente so a quantidade
        if pid == meu_id:
            minhas_cartas = dados.get("cartas", [])
            n = len(minhas_cartas)
            if n == 0:
                exibicao_cartas = "nenhuma"
            else:
                exibicao_cartas = ", ".join(minhas_cartas)
                contagem = Counter(minhas_cartas)
                pode_trocar = any(v >= 3 for v in contagem.values()) or len(set(minhas_cartas)) >= 3
                if n >= 3 and pode_trocar:
                    exibicao_cartas += "  [PODE TROCAR]"
            print(f"       Suas cartas ({n}): {exibicao_cartas}")
        else:
            quantidade_cartas_oponente = dados.get("quantidade_cartas", 0)
            print(f"       Cartas do oponente: {quantidade_cartas_oponente} carta(s)")
    print()

    # Mapa por continente
    print("  MAPA:")
    for nome_continente, dados_continente in CONTINENTES.items():
        territorios_do_continente = dados_continente["territorios"]
        donos = {territorios[t]["dono"] for t in territorios_do_continente if t in territorios}

        if len(donos) == 1 and None not in donos:
            pid_dono   = next(iter(donos))
            nome_dono  = jogadores.get(pid_dono, {}).get("nome", f"J{pid_dono}")
            label_cont = f" [Dominado por {nome_dono} - Bonus +{dados_continente['bonus']}]"
        else:
            label_cont = f" [Bonus continental: +{dados_continente['bonus']}]"

        print(f"  +-- {nome_continente}{label_cont}")
        for t in territorios_do_continente:
            if t not in territorios:
                continue
            td   = territorios[t]
            dono = td["dono"]
            if dono == meu_id:
                tag_dono = "SEU"
            elif dono:
                tag_dono = f"J{dono}"
            else:
                tag_dono = "----"
            adjacencias = ", ".join(ADJACENCIAS.get(t, []))
            print(f"  |  [{tag_dono}] {t:20s} {td['tropas']:2d} tropa(s)   adj: {adjacencias}")
        print("  |")
    print()

    # Registro das ultimas acoes
    print("  ULTIMAS ACOES:")
    for entrada in estado["registro"][-6:]:
        print(f"    {entrada}")
    print()
    print("-" * 66)



# Acoes do jogador (cada funcao representa uma etapa do turno)


def acao_posicionamento_inicial(jogo, meu_id: str, estado: dict):
    """
    Posicionamento inicial: o jogador escolhe um de seus territorios
    e coloca quantas tropas quiser das que ainda tem disponiveis.
    """
    territorios    = estado["territorios"]
    tropas_restantes = estado["jogadores"][meu_id]["tropas_para_colocar"]
    meus_territorios = [nome for nome, td in territorios.items() if td["dono"] == meu_id]

    print(f"\n  == POSICIONAMENTO INICIAL ==  Tropas restantes: {tropas_restantes}\n")

    territorio = escolher_territorio_da_lista("Escolha seu territorio", meus_territorios)
    if territorio is None:
        return

    quantidade = escolher_numero(
        f"  Quantas tropas em {territorio}? (1-{tropas_restantes}): ", 1, tropas_restantes
    ) if tropas_restantes > 1 else 1
    if quantidade is None:
        return

    resultado = jogo.colocar_tropas(meu_id, territorio, quantidade)
    if resultado["sucesso"]:
        print(f"  OK: {quantidade} tropa(s) colocada(s) em {territorio}.")
    else:
        print(f"  ERRO: {resultado['mensagem']}")
    time.sleep(0.8)


def acao_distribuir_reforcos(jogo, meu_id: str, estado: dict):
    """
    Distribuicao de reforcos: o jogador aloca as tropas recebidas
    no inicio do turno antes de poder atacar.
    """
    territorios      = estado["territorios"]
    tropas_restantes = estado["jogadores"][meu_id]["tropas_para_colocar"]
    meus_territorios = [nome for nome, td in territorios.items() if td["dono"] == meu_id]

    print(f"\n  == DISTRIBUIR REFORCOS ==  Tropas a distribuir: {tropas_restantes}\n")

    territorio = escolher_territorio_da_lista("Escolha o territorio para reforcar", meus_territorios)
    if territorio is None:
        return

    quantidade = escolher_numero(
        f"  Quantas tropas em {territorio}? (1-{tropas_restantes}): ", 1, tropas_restantes
    ) if tropas_restantes > 1 else 1
    if quantidade is None:
        return

    resultado = jogo.colocar_tropas(meu_id, territorio, quantidade)
    if resultado["sucesso"]:
        print(f"  OK: {quantidade} tropa(s) enviada(s) para {territorio}.")
    else:
        print(f"  ERRO: {resultado['mensagem']}")
    time.sleep(0.6)


def acao_trocar_cartas(jogo, meu_id: str, estado: dict):
    """
    Troca de cartas: exibe as cartas do jogador, verifica se ha combinacao
    valida e envia a escolha ao servidor.
    Combinacoes validas: 3 iguais  ou  1 de cada tipo (3 diferentes).
    """
    cartas = estado["jogadores"][meu_id].get("cartas", [])
    n      = len(cartas)

    if n < 3:
        print(f"  Voce tem apenas {n} carta(s). Precisa de pelo menos 3.")
        time.sleep(1.5)
        return

    print("\n  == TROCA DE CARTAS ==")
    print(f"  Suas cartas ({n}):")
    for i, carta in enumerate(cartas, 1):
        print(f"    {i}. {carta}")

    contagem      = Counter(cartas)
    tipos_unicos  = set(cartas)
    print(f"\n  Combinacoes validas: 3 iguais  |  1 de cada tipo (3 diferentes)")
    print(f"  Resumo das suas cartas: {dict(contagem)}")

    tem_tres_iguais  = any(v >= 3 for v in contagem.values())
    tem_uma_de_cada  = len(tipos_unicos) >= 3
    if not (tem_tres_iguais or tem_uma_de_cada):
        print("  Ainda sem combinacao valida disponivel.")
        time.sleep(1.5)
        return

    escolha = perguntar("\n  Digite os 3 numeros das cartas separados por espaco (ou Enter para cancelar): ")
    if not escolha:
        return

    try:
        indices = [int(x) - 1 for x in escolha.split()]
    except ValueError:
        print("  Entrada invalida."); time.sleep(1); return

    resultado = jogo.trocar_cartas_por_tropas(meu_id, indices)
    if resultado["sucesso"]:
        print(f"\n  OK: Cartas trocadas: {resultado['escolhidas']}")
        print(f"  OK: +{resultado['bonus']} tropas adicionadas aos seus reforcos!")
    else:
        print(f"  ERRO: {resultado['mensagem']}")
    time.sleep(1.2)


def acao_mover_tropas(jogo, meu_id: str, estado: dict):
    """
    Movimentacao (Fortificacao): transfere tropas entre dois territorios
    proprios e adjacentes. Pode ser feita uma unica vez por turno.
    """
    territorios = estado["territorios"]
    meus_territorios_com_2_ou_mais = [
        nome for nome, td in territorios.items()
        if td["dono"] == meu_id and td["tropas"] >= 2
    ]

    if not meus_territorios_com_2_ou_mais:
        print("  Nenhum territorio com tropas suficientes para mover (precisa de 2 ou mais).")
        time.sleep(1.5)
        return

    print("\n  == MOVIMENTACAO DE TROPAS ==")
    print("  Transfere tropas entre dois territorios seus adjacentes (uma vez por turno).\n")

    origem = escolher_territorio_da_lista(
        "Territorio de ORIGEM (2 ou mais tropas)", meus_territorios_com_2_ou_mais
    )
    if origem is None:
        return

    # Destinos validos: territorios proprios adjacentes a origem
    destinos_validos = [
        adj for adj in ADJACENCIAS.get(origem, [])
        if territorios.get(adj, {}).get("dono") == meu_id
    ]

    if not destinos_validos:
        print(f"  {origem} nao tem territorios seus adjacentes para receber tropas.")
        time.sleep(1.5)
        return

    print(f"\n  Origem: {origem} ({territorios[origem]['tropas']} tropas)")
    destino = escolher_territorio_da_lista("Territorio de DESTINO", destinos_validos)
    if destino is None:
        return

    maximo_para_mover = territorios[origem]["tropas"] - 1
    quantidade = escolher_numero(
        f"  Quantas tropas mover? (1-{maximo_para_mover}): ", 1, maximo_para_mover
    )
    if quantidade is None:
        return

    resultado = jogo.mover_tropas_entre_territorios(meu_id, origem, destino, quantidade)
    if resultado["sucesso"]:
        print(f"  OK: {quantidade} tropa(s) transferida(s): {origem} -> {destino}.")
    else:
        print(f"  ERRO: {resultado['mensagem']}")
    time.sleep(0.8)


def acao_atacar_ou_encerrar_turno(jogo, meu_id: str, estado: dict) -> str | None:
    """
    Menu principal do turno de batalha. O jogador escolhe entre:
      1. Atacar um territorio inimigo adjacente
      2. Mover tropas entre seus territorios (uma vez por turno)
      3. Encerrar o turno
    Retorna "venceu" se o jogador venceu, None caso contrario.
    """
    territorios   = estado["territorios"]
    jogadores     = estado["jogadores"]
    jogador_moveu = estado.get("jogador_moveu_tropas", False)

    # Calcula todos os ataques possiveis
    ataques_possiveis = []
    for origem, td in territorios.items():
        if td["dono"] == meu_id and td["tropas"] >= 2:
            for vizinho in ADJACENCIAS.get(origem, []):
                dados_vizinho = territorios.get(vizinho, {})
                if dados_vizinho.get("dono") and dados_vizinho["dono"] != meu_id:
                    ataques_possiveis.append((origem, vizinho))

    print("\n  == TURNO DE BATALHA ==\n")
    print("  O que deseja fazer?")
    print("    1. Atacar territorio inimigo")

    if not jogador_moveu:
        print("    2. Mover tropas entre seus territorios")
        print("    3. Encerrar turno")
    else:
        print("    2. Encerrar turno  (movimentacao ja realizada neste turno)")

    acao = perguntar("\n  Escolha: ")

    # Encerrar turno
    encerrando = (acao == "3") or (acao == "2" and jogador_moveu)
    if encerrando:
        resultado = jogo.encerrar_turno(meu_id)
        if resultado["sucesso"]:
            if resultado.get("carta_recebida"):
                print(f"\n  Voce ganhou uma carta: {resultado['carta_recebida']}!")
                print("  (O oponente nao sabe qual carta voce recebeu.)")
                time.sleep(2)   # 2 segundos para o jogador ver a carta
            else:
                print("  Turno encerrado.")
                time.sleep(0.6)
        else:
            print(f"  ERRO: {resultado['mensagem']}")
        return None

    # Mover tropas
    if acao == "2" and not jogador_moveu:
        acao_mover_tropas(jogo, meu_id, estado)
        return None

    # Atacar
    if acao != "1":
        print("  Opcao invalida.")
        return None

    if not ataques_possiveis:
        print("  Nenhum ataque possivel (precisa de 2 ou mais tropas adjacentes a um inimigo).")
        time.sleep(1.5)
        return None

    print("\n  Ataques disponiveis:")
    for i, (origem, alvo) in enumerate(ataques_possiveis, 1):
        tropas_origem = territorios[origem]["tropas"]
        tropas_alvo   = territorios[alvo]["tropas"]
        dono_alvo     = territorios[alvo]["dono"]
        nome_dono     = jogadores.get(dono_alvo, {}).get("nome", f"J{dono_alvo}")
        print(f"    {i:2}. {origem} ({tropas_origem} tropas) -> {alvo} ({tropas_alvo} tropas | {nome_dono})")

    escolha = perguntar("\n  Numero do ataque (ou 'v' para voltar): ")
    if escolha.lower() == "v":
        return None

    try:
        idx = int(escolha) - 1
        if idx < 0 or idx >= len(ataques_possiveis):
            print("  Numero invalido."); return None
    except ValueError:
        print("  Entrada invalida."); return None

    origem, alvo = ataques_possiveis[idx]
    max_dados    = min(3, territorios[origem]["tropas"] - 1)

    print(f"\n  Atacando: {origem} -> {alvo}")
    print(f"  Dados de ataque disponiveis: 1 a {max_dados}  (defensor usa ate 2 dados)")

    num_dados = escolher_numero(f"  Quantos dados de ataque? (1-{max_dados}): ", 1, max_dados)
    if num_dados is None:
        return None

    resultado = jogo.atacar_territorio(meu_id, origem, alvo, num_dados)
    if not resultado["sucesso"]:
        print(f"  ERRO: {resultado['mensagem']}"); time.sleep(1); return None

    print()
    print(f"  Dados de ataque : {resultado['dados_ataque']}")
    print(f"  Dados de defesa : {resultado['dados_defesa']}")
    print()
    print(f"  Baixas: voce perdeu {resultado['baixas_ataque']} | inimigo perdeu {resultado['baixas_defesa']}")

    if resultado["conquistado"]:
        print(f"\n  Voce conquistou {alvo}!")

    if resultado.get("vencedor"):
        print("\n  +---------------------------+")
        print("  |   VOCE VENCEU O JOGO!    |")
        print("  +---------------------------+")
        time.sleep(4)
        return "venceu"

    time.sleep(1.2)
    return None


# -------------------------------------------------------------------------
# Loop principal do jogo
# -------------------------------------------------------------------------

def executar_loop_do_jogo(jogo, meu_id: str):
    """
    Loop principal: busca o estado do servidor a cada iteracao (polling),
    exibe o mapa e chama a acao correta de acordo com a fase e o turno.
    """
    while True:
        try:
            estado = jogo.obter_estado_do_jogo(meu_id)
        except Exception as e:
            print(f"Erro de comunicacao com o servidor: {e}")
            time.sleep(2)
            continue

        exibir_estado_do_jogo(estado, meu_id)

        fase          = estado["fase"]
        jogador_atual = estado["jogador_atual"]

        # Fim de jogo
        if fase == "encerrado":
            vencedor = estado["vencedor"]
            if vencedor == meu_id:
                print("  PARABENS! VOCE DOMINOU O MUNDO!")
            else:
                nome_vencedor = estado["jogadores"].get(vencedor, {}).get("nome", f"Jogador {vencedor}")
                print(f"  Fim de jogo. {nome_vencedor} dominou o mundo.")
            break

        # Aguardando segundo jogador
        if fase == "aguardando":
            print("  Aguardando o segundo jogador conectar...")
            time.sleep(2)
            continue

        # Vez do oponente
        if jogador_atual != meu_id:
            nome_oponente = estado["jogadores"].get(jogador_atual, {}).get("nome", f"Jogador {jogador_atual}")
            print(f"  Aguardando {nome_oponente} jogar...")
            time.sleep(2)
            continue

        # Minha vez
        tropas_restantes = estado["jogadores"][meu_id]["tropas_para_colocar"]
        minhas_cartas    = estado["jogadores"][meu_id].get("cartas", [])

        if fase == "posicionamento":
            if tropas_restantes > 0:
                acao_posicionamento_inicial(jogo, meu_id, estado)
            else:
                print("  Posicionamento concluido. Aguardando o outro jogador...")
                time.sleep(2)

        elif fase == "batalha":
            # Oferecer troca de cartas antes dos reforcos, se houver combinacao valida
            if len(minhas_cartas) >= 3 and tropas_restantes > 0:
                contagem = Counter(minhas_cartas)
                pode_trocar = any(v >= 3 for v in contagem.values()) or len(set(minhas_cartas)) >= 3
                if pode_trocar:
                    exibir_estado_do_jogo(estado, meu_id)
                    print(f"  Voce tem {len(minhas_cartas)} carta(s) e pode trocar antes de distribuir reforcos!")
                    resposta = perguntar("  Deseja trocar cartas agora? (s/n): ")
                    if resposta.lower() == "s":
                        acao_trocar_cartas(jogo, meu_id, estado)
                        continue

            if tropas_restantes > 0:
                acao_distribuir_reforcos(jogo, meu_id, estado)
            else:
                resultado = acao_atacar_ou_encerrar_turno(jogo, meu_id, estado)
                if resultado == "venceu":
                    break





# -------------------------------------------------------------------------
# Inicializacao do cliente
# -------------------------------------------------------------------------

def main():
    print("Cliente do Risk - Pyro5 / RMI")
    print("-" * 35)

    nome_jogador = perguntar("Seu nome: ") or "Guerreiro"

    print("\nConectando ao servidor...")
    try:
        jogo = Pyro5.api.Proxy("PYRONAME:risk.jogo")
        jogo._pyroBind()
    except Exception as e:
        print(f"\n[ERRO] Nao foi possivel conectar: {e}")
        print("Verifique se o servidor de nomes e o servidor do jogo estao rodando.")
        sys.exit(1)

    resultado = jogo.entrar_no_jogo(nome_jogador)
    if not resultado["sucesso"]:
        print(f"\n[ERRO] {resultado['mensagem']}")
        sys.exit(1)

    meu_id = resultado["id_jogador"]
    print(f"\nConectado! Voce e o Jogador {meu_id} ({nome_jogador})")
    if meu_id == "1":
        print("Aguardando o Jogador 2 entrar...")

    time.sleep(1)
    executar_loop_do_jogo(jogo, meu_id)

    print("\nAte a proxima! Pressione Enter para sair.")
    perguntar("")


if __name__ == "__main__":
    main()
