# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, func, select, update
from datetime import datetime
from sqlalchemy import UniqueConstraint, JSON
from sqlalchemy.exc import IntegrityError

from config.settings import *

# ------------------------------------------------------------------
# Database Setup
# ------------------------------------------------------------------
Base = declarative_base()

DATABASE_URL = "sqlite+aiosqlite:///data/nepse_bot.db"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------
class Security(Base):
    __tablename__ = "securities"

    symbol = Column(String(20), primary_key=True)
    exchange_security_id = Column(Integer, nullable=False, unique=True)   # WS argument
    security_id = Column(Integer, nullable=False, unique=True)            # order payload "id"
    last_pre_close = Column(Numeric(10, 2), nullable=True)                # yesterday's close (pcp)
    # circuit_price = Column(Numeric(10, 2), nullable=True)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    


class TradeConfig(Base):
    __tablename__ = "trade_config"

    symbol = Column(String(20), primary_key=True)
    quantity = Column(Integer, nullable=False, default=10)
    enabled = Column(Boolean, default=True)
    notes = Column(String(200), nullable=True)

class FirstOrderExecution(Base):
    __tablename__ = "first_order_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD (Nepal)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), nullable=False)  # "sent", "accepted", "failed"
    details = Column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_symbol_date"),)



        
        
        
# ------------------------------------------------------------------
# DB Init
# ------------------------------------------------------------------
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ------------------------------------------------------------------
# Helper Functions (used everywhere)
# ------------------------------------------------------------------
async def get_security(symbol: str) -> Security | None:
    async with AsyncSessionLocal() as db:
        result = await db.get(Security, symbol)
        return result


async def get_trade_config(symbol: str) -> TradeConfig | None:
    async with AsyncSessionLocal() as db:
        result = await db.get(TradeConfig, symbol)
        return result


async def save_or_update_security(symbol: str, exchange_id: int, sec_id: int, pre_close: float | None = None):
    async with AsyncSessionLocal() as db:
        sec = await db.get(Security, symbol)
        if sec:
            sec.exchange_security_id = exchange_id
            sec.security_id = sec_id
            if pre_close is not None:
                sec.last_pre_close = pre_close
        else:
            db.add(Security(
                symbol=symbol,
                exchange_security_id=exchange_id,
                security_id=sec_id,
                last_pre_close=pre_close
            ))
        await db.commit()


async def update_pre_close_and_circuit_price(symbol: str, price: float):
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Security)
            .where(Security.symbol == symbol)
            .values(
                last_pre_close=price, 
                # circuit_price = price * DAILY_CIRCUIT
            )
        )
        await db.commit()


async def save_trade_config(symbol: str, quantity: int, enabled: bool = True, notes: str | None = None):
    async with AsyncSessionLocal() as db:
        cfg = await db.get(TradeConfig, symbol)
        if cfg:
            cfg.quantity = quantity
            cfg.enabled = enabled
            cfg.notes = notes
        else:
            db.add(TradeConfig(symbol=symbol, quantity=quantity, enabled=enabled, notes=notes))
        await db.commit()


async def get_all_enabled_symbols() -> list[dict]:
    """Returns list of dicts with everything we need for the main loop"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Security, TradeConfig)
            .join(TradeConfig, Security.symbol == TradeConfig.symbol)
            .where(TradeConfig.enabled == True)
        )
        rows = result.all()
        return [
            {
                "symbol": sec.symbol,
                "exchange_security_id": sec.exchange_security_id,
                "security_id": sec.security_id,
                "last_pre_close": float(sec.last_pre_close) if sec.last_pre_close else None,
                "quantity": cfg.quantity,
            }
            for sec, cfg in rows
        ]



async def get_all_trade_config_symbols() -> list[str]:
    """Return all symbols currently present in trade_config table (enabled or not)."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(TradeConfig.symbol))).scalars().all()
        return list(rows)


async def set_trade_config_enabled(symbol: str, enabled: bool) -> None:
    """Set trade_config.enabled for `symbol`."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(TradeConfig).where(TradeConfig.symbol == symbol).values(enabled=enabled)
        )
        await session.commit()
        
        
        
# Helper APIs for startup-first-order logic
async def has_first_order_executed(symbol: str, date_str: str) -> bool:
    """Return True if a first-order execution exists for symbol on date_str (YYYY-MM-DD)."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(FirstOrderExecution.id).where(
                FirstOrderExecution.symbol == symbol,
                FirstOrderExecution.date == date_str
            )
        )
        return res.scalars().first() is not None


async def record_first_order_execution(symbol: str, date_str: str, status: str, details: dict | None = None) -> None:
    """Insert a FirstOrderExecution row (safe: ignores duplicate unique constraint)."""
    async with AsyncSessionLocal() as session:
        fo = FirstOrderExecution(symbol=symbol, date=date_str, status=status, details=details)
        session.add(fo)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()  # already recorded by another process/run
            return