import logging
from config import TARGET_DIGITS, SPECIAL_DIGITS, PROFIT_TARGET, set_rokada_status, get_rokada_status

logger = logging.getLogger(__name__)


def is_rounded_zero(price):
    price_str = f"{price:.5f}"
    return price_str.endswith("0")


def generate_signals(current_price, walls, trend, rokada_status="off"):
    logger.info(f"Ulaz u generate_signals: current_price={current_price}, trend={trend}, rokada={rokada_status}")
    signals = []

    support_walls = sorted(walls.get('support', []), key=lambda x: x[1], reverse=True) if walls else []
    resistance_walls = sorted(walls.get('resistance', []), key=lambda x: x[1], reverse=True) if walls else []

    if current_price is None:
        logger.warning("current_price je None, preskačem generisanje signala")
        return signals

    logger.info(f"Support walls: {len(support_walls)}, Resistance walls: {len(resistance_walls)}")

    # Automatski uključivanje rokada_status ako postoje jaki zidovi
    if len(support_walls) > 0 or len(resistance_walls) > 0:
        set_rokada_status("on")
        rokada_status = get_rokada_status()
        logger.info("Rokada status automatski uključen zbog prisutnih zidova")

    for price, volume in support_walls:
        last_digit = int(str(round(price, 4))[-1])
        rounded_zero = is_rounded_zero(price)
        logger.debug(
            f"Support wall: price={price:.5f}, last_digit={last_digit}, rounded_zero={rounded_zero}, volume={volume:.2f}")
        if last_digit in TARGET_DIGITS:
            if last_digit in [2, 3]:
                signal = {
                    'type': 'LONG',
                    'entry_price': price,
                    'stop_loss': round(price - 0.00005, 5),
                    'take_profit': round(price + PROFIT_TARGET, 5),
                    'volume': volume,
                    'confidence': min(0.9, volume / 100)
                }
                signals.append(signal)
                logger.info(f"Signal: {signal}")
        elif rokada_status == "on" and last_digit in SPECIAL_DIGITS and trend == 'DOWN':
            if last_digit == 1 and rounded_zero:
                signal = {
                    'type': 'SHORT',
                    'entry_price': round(price - 0.00002, 5),
                    'stop_loss': round(price + 0.00005, 5),
                    'take_profit': round(price - PROFIT_TARGET, 5),
                    'volume': volume,
                    'confidence': min(0.9, volume / 100)
                }
                signals.append(signal)
                logger.info(f"Signal: {signal}")

    for price, volume in resistance_walls:
        last_digit = int(str(round(price, 4))[-1])
        rounded_zero = is_rounded_zero(price)
        logger.debug(
            f"Resistance wall: price={price:.5f}, last_digit={last_digit}, rounded_zero={rounded_zero}, volume={volume:.2f}")
        if last_digit in TARGET_DIGITS:
            if last_digit in [7, 8]:
                signal = {
                    'type': 'SHORT',
                    'entry_price': price,
                    'stop_loss': round(price + 0.00005, 5),
                    'take_profit': round(price - PROFIT_TARGET, 5),
                    'volume': volume,
                    'confidence': min(0.9, volume / 100)
                }
                signals.append(signal)
                logger.info(f"Signal: {signal}")
        elif rokada_status == "on" and last_digit in SPECIAL_DIGITS and trend == 'UP':
            if last_digit == 9 and rounded_zero:
                signal = {
                    'type': 'LONG',
                    'entry_price': round(price + 0.00002, 5),
                    'stop_loss': round(price - 0.00005, 5),
                    'take_profit': round(price + PROFIT_TARGET, 5),
                    'volume': volume,
                    'confidence': min(0.9, volume / 100)
                }
                signals.append(signal)
                logger.info(f"Signal: {signal}")

    logger.info(f"Generisano signala: {len(signals)}")
    return signals
    
    