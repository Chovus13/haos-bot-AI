import os
from dotenv import load_dotenv

load_dotenv()

# Trading par
PAR = os.getenv('ETHBTC', 'ETH/BTC')

# Postavke za zidove
MIN_WALL_VOLUME = float(os.getenv('MIN_WALL_VOLUME', 1))
WALL_RANGE_SPREAD = float(os.getenv('WALL_RANGE_SPREAD', 0.0001))

# Preciznost
PRICE_PRECISION = int(os.getenv('PRICE_PRECISION', 5))

# Strategija
TARGET_DIGITS = [int(d) for d in os.getenv('TARGET_DIGITS', '2,3,7,8').split(',')]
SPECIAL_DIGITS = [int(d) for d in os.getenv('SPECIAL_DIGITS', '1,9').split(',')]
PROFIT_TARGET = float(os.getenv('PROFIT_TARGET', 0.00010))

# Parametri za trejd
AMOUNT = float(os.getenv('AMOUNT', 0.05))
LEVERAGE = int(os.getenv('LEVERAGE', 1))  # Ispravljeno na 1

# Rokada status
rokada_status = "off"

def set_rokada_status(status: str) -> bool:
    global rokada_status
    if status.lower() in ["on", "off"]:
        rokada_status = status.lower()
        return True
    return False

def get_rokada_status() -> str:
    return rokada_status
    


#def get_rokada_status():
#    return rokada_status
#
#def set_rokada_status(status):
#
#    global rokada_status
#    if status in ["on", "off"]:
#        rokada_status = status
#       return True
#   return False