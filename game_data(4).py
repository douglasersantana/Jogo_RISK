# game_data.py
# Dados compartilhados do mapa do jogo Risk simplificado.
# Importado tanto pelo servidor quanto pelo cliente.
#
# Mapa: 15 territorios, 4 continentes
# Cartas: 3 tipos, bonus fixo de 6 tropas por troca


# -------------------------------------------------------------------------
# Continentes
# Cada continente define quais territorios o compoe e qual bonus de tropas
# o jogador recebe por turno ao controlar todos os seus territorios.
# -------------------------------------------------------------------------

CONTINENTES = {
    "America": {
        "territorios": ["Alaska", "Mexico", "Brasil", "Argentina"],
        "bonus": 3
    },
    "Europa": {
        "territorios": ["Franca", "Inglaterra", "Alemanha", "Russia"],
        "bonus": 3
    },
    "Asia": {
        "territorios": ["China", "India", "Japao", "Arabia"],
        "bonus": 4
    },
    "Africa": {
        "territorios": ["Egito", "Nigeria", "Africa do Sul"],
        "bonus": 2
    }
}


# -------------------------------------------------------------------------
# Adjacencias
# Para cada territorio, lista os territorios com os quais faz fronteira.
# Um ataque so e valido entre territorios adjacentes.
# Toda adjacencia e bidirecional: se A lista B, entao B lista A.
#
# Conexoes maritimas incluidas:
#   Alaska  <-> Japao        (via Pacifico)
#   Brasil  <-> Nigeria      (via Atlantico)
#   Franca  <-> Egito        (via Mediterraneo)
# -------------------------------------------------------------------------

ADJACENCIAS = {
    # America
    "Alaska":        ["Mexico", "Japao"],
    "Mexico":        ["Alaska", "Brasil"],
    "Brasil":        ["Mexico", "Argentina", "Nigeria"],
    "Argentina":     ["Brasil"],

    # Europa
    "Franca":        ["Inglaterra", "Alemanha", "Egito"],
    "Inglaterra":    ["Franca", "Alemanha"],
    "Alemanha":      ["Franca", "Inglaterra", "Russia"],
    "Russia":        ["Alemanha", "Arabia", "China"],

    # Asia
    "China":         ["Russia", "India", "Japao"],
    "India":         ["China", "Arabia"],
    "Japao":         ["China", "Alaska"],
    "Arabia":        ["India", "Russia", "Egito"],

    # Africa
    "Egito":         ["Franca", "Arabia", "Nigeria"],
    "Nigeria":       ["Egito", "Brasil", "Africa do Sul"],
    "Africa do Sul": ["Nigeria"],
}


# -------------------------------------------------------------------------
# Lista de todos os territorios (gerada automaticamente das chaves acima)
# -------------------------------------------------------------------------

TODOS_OS_TERRITORIOS = list(ADJACENCIAS.keys())   # 15 territorios no total


# -------------------------------------------------------------------------
# Cartas
# Ao conquistar pelo menos 1 territorio por turno, o jogador recebe
# uma carta aleatoria ao encerrar o turno.
# Combinacoes validas para troca: 3 iguais  ou  1 de cada tipo.
# -------------------------------------------------------------------------

TIPOS_DE_CARTA = [
    "Infantaria",
    "Cavalaria",
    "Artilharia"
]

BONUS_TROCA_CARTAS = 6   # tropas extras recebidas ao trocar 3 cartas
