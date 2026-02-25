"""
Options chain processor: computes PCR, Max Pain, IV Rank.
"""
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from collections import defaultdict
import pytz
import redis
import json
from loguru import logger

from api.config import settings
from data.kite_client import kite_client

IST = pytz.timezone(settings.ist_timezone)
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

REDIS_OPTIONS_KEY = "options:latest"
REDIS_PCR_KEY = "options:pcr"
REDIS_MAX_PAIN_KEY = "options:max_pain"
REDIS_IV_RANK_KEY = "options:iv_rank"
REDIS_TTL = 600  # 10 minutes


class OptionsProcessor:
    """
    Processes raw options chain data into trading metrics.
    """

    def compute_pcr(self, chain: List[Dict]) -> Decimal:
        """
        Put-Call Ratio = Total PE OI / Total CE OI
        PCR > 1.2 → Bearish sentiment
        PCR < 0.8 → Bullish sentiment
        """
        total_ce_oi = sum(item.get("oi", 0) for item in chain if item.get("option_type") == "CE")
        total_pe_oi = sum(item.get("oi", 0) for item in chain if item.get("option_type") == "PE")

        if total_ce_oi == 0:
            return Decimal("1.0")
        return Decimal(str(total_pe_oi)) / Decimal(str(total_ce_oi))

    def compute_max_pain(self, chain: List[Dict], underlying: Decimal) -> Decimal:
        """
        Max Pain = strike where total option writer loss is minimized.
        Calculated as sum of losses for both CE and PE writers at each strike.
        """
        # Group by strike
        strikes: Dict[Decimal, Dict] = defaultdict(lambda: {"CE_OI": 0, "PE_OI": 0})
        for item in chain:
            strike = Decimal(str(item.get("strike", 0)))
            oi = item.get("oi", 0) or 0
            if item.get("option_type") == "CE":
                strikes[strike]["CE_OI"] += oi
            else:
                strikes[strike]["PE_OI"] += oi

        if not strikes:
            return underlying

        all_strikes = sorted(strikes.keys())
        min_pain = None
        max_pain_strike = underlying

        for test_strike in all_strikes:
            total_pain = Decimal("0")
            for strike, oi_data in strikes.items():
                # CE writers lose when price > strike
                if test_strike > strike:
                    total_pain += (test_strike - strike) * Decimal(str(oi_data["CE_OI"]))
                # PE writers lose when price < strike
                if test_strike < strike:
                    total_pain += (strike - test_strike) * Decimal(str(oi_data["PE_OI"]))

            if min_pain is None or total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_strike

        return max_pain_strike

    def compute_iv_rank(self, current_iv: Decimal, iv_history: List[Decimal]) -> Decimal:
        """
        IV Rank = (Current IV - 52w Low) / (52w High - 52w Low) * 100
        """
        if not iv_history or len(iv_history) < 2:
            return Decimal("50.0")

        low_iv = min(iv_history)
        high_iv = max(iv_history)

        if high_iv == low_iv:
            return Decimal("50.0")

        rank = (current_iv - low_iv) / (high_iv - low_iv) * Decimal("100")
        return max(Decimal("0"), min(Decimal("100"), rank))

    def get_atm_iv(self, chain: List[Dict], underlying: Decimal) -> Decimal:
        """Get IV of the nearest ATM strike."""
        if not chain:
            return Decimal("20.0")

        atm_items = sorted(
            [item for item in chain if item.get("iv", 0)],
            key=lambda x: abs(Decimal(str(x.get("strike", 0))) - underlying)
        )
        if not atm_items:
            return Decimal("20.0")

        iv = Decimal(str(atm_items[0].get("iv", 20)))
        return iv if iv > 0 else Decimal("20.0")

    def process_and_cache(self, underlying: Optional[Decimal] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch, process, and cache options metrics in Redis.
        Returns processed options summary.
        """
        raw = kite_client.get_options_chain()
        if not raw:
            # Return cached data if available
            cached = redis_client.get(REDIS_OPTIONS_KEY)
            if cached:
                return json.loads(cached)
            return self._get_mock_options(underlying)

        chain = raw["chain"]
        expiry = raw["expiry"]

        if underlying is None:
            quote = kite_client.get_live_quote()
            underlying = quote["ltp"] if quote else Decimal("48000")

        pcr = self.compute_pcr(chain)
        max_pain = self.compute_max_pain(chain, underlying)
        atm_iv = self.get_atm_iv(chain, underlying)

        # IV Rank: fetch historical from Redis
        iv_history_raw = redis_client.lrange("iv_history", 0, -1)
        iv_history = [Decimal(v) for v in iv_history_raw] if iv_history_raw else []
        if atm_iv > 0:
            redis_client.rpush("iv_history", str(atm_iv))
            redis_client.ltrim("iv_history", -252, -1)  # Keep ~1 year of daily IVs

        iv_rank = self.compute_iv_rank(atm_iv, iv_history or [atm_iv])

        # Format chain for response
        chain_by_strike: Dict[Decimal, Dict] = defaultdict(dict)
        for item in chain:
            strike = Decimal(str(item["strike"]))
            opt_type = item["option_type"]
            chain_by_strike[strike][opt_type] = item

        formatted_chain = []
        for strike in sorted(chain_by_strike.keys()):
            data = chain_by_strike[strike]
            ce = data.get("CE", {})
            pe = data.get("PE", {})
            formatted_chain.append({
                "strike": float(strike),
                "ce_ltp": float(ce.get("ltp", 0)),
                "ce_oi": ce.get("oi", 0),
                "ce_change_oi": ce.get("change_oi", 0),
                "ce_iv": float(ce.get("iv", 0)),
                "pe_ltp": float(pe.get("ltp", 0)),
                "pe_oi": pe.get("oi", 0),
                "pe_change_oi": pe.get("change_oi", 0),
                "pe_iv": float(pe.get("iv", 0)),
            })

        result = {
            "symbol": "BANKNIFTY",
            "expiry": expiry,
            "pcr": float(pcr),
            "max_pain": float(max_pain),
            "iv_rank": float(iv_rank),
            "atm_iv": float(atm_iv),
            "underlying_price": float(underlying),
            "timestamp": datetime.now(IST).isoformat(),
            "chain": formatted_chain,
        }

        # Cache in Redis
        redis_client.setex(REDIS_OPTIONS_KEY, REDIS_TTL, json.dumps(result))
        redis_client.setex(REDIS_PCR_KEY, REDIS_TTL, str(float(pcr)))
        redis_client.setex(REDIS_MAX_PAIN_KEY, REDIS_TTL, str(float(max_pain)))
        redis_client.setex(REDIS_IV_RANK_KEY, REDIS_TTL, str(float(iv_rank)))

        logger.debug(f"Options cached: PCR={pcr:.2f} MaxPain={max_pain:.0f} IVRank={iv_rank:.1f}%")
        return result

    def get_cached_pcr(self) -> Decimal:
        """Get PCR from Redis cache."""
        val = redis_client.get(REDIS_PCR_KEY)
        return Decimal(val) if val else Decimal("1.0")

    def get_cached_max_pain(self) -> Decimal:
        """Get Max Pain from Redis cache."""
        val = redis_client.get(REDIS_MAX_PAIN_KEY)
        return Decimal(val) if val else Decimal("48000")

    def get_cached_iv_rank(self) -> Decimal:
        """Get IV Rank from Redis cache."""
        val = redis_client.get(REDIS_IV_RANK_KEY)
        return Decimal(val) if val else Decimal("50.0")

    def _get_mock_options(self, underlying: Optional[Decimal]) -> Dict[str, Any]:
        """Return mock options data for demo/fallback."""
        ltp = float(underlying) if underlying else 48000
        strikes = [round(ltp / 100) * 100 + i * 100 for i in range(-10, 11)]
        chain = []
        for s in strikes:
            dist = abs(s - ltp)
            chain.append({
                "strike": s,
                "ce_ltp": max(0.05, ltp - s + 50 + dist * 0.1) if s < ltp else max(0.05, 50 - (s - ltp) * 0.3),
                "ce_oi": 100000 - int(dist * 10),
                "ce_change_oi": int(dist * 5),
                "ce_iv": 15 + dist * 0.01,
                "pe_ltp": max(0.05, s - ltp + 50 + dist * 0.1) if s > ltp else max(0.05, 50 - (ltp - s) * 0.3),
                "pe_oi": 120000 - int(dist * 10),
                "pe_change_oi": -int(dist * 3),
                "pe_iv": 16 + dist * 0.01,
            })
        return {
            "symbol": "BANKNIFTY",
            "expiry": "2024-12-26",
            "pcr": 0.85,
            "max_pain": round(ltp / 100) * 100,
            "iv_rank": 35.0,
            "atm_iv": 16.5,
            "underlying_price": ltp,
            "timestamp": datetime.now(IST).isoformat(),
            "chain": chain,
        }


# Singleton
options_processor = OptionsProcessor()
