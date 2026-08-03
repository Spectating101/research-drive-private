#!/usr/bin/env python3
"""
Enhanced Daily Operation Script for Advanced Trading System

This script integrates all advanced modules:
- Machine Learning signal generation
- Market microstructure analysis
- Advanced portfolio optimization
- Regime detection and adaptation
- Cross-validation and performance monitoring

Features:
- Multi-model signal generation
- Microstructure-aware trading
- Sophisticated portfolio optimization
- Real-time performance monitoring
- Automated risk management
"""

import sys
import os
import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/enhanced_operation.log')
    ]
)
logger = logging.getLogger(__name__)

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import advanced modules
try:
    from src.ml.advanced_signals import AdvancedSignalGenerator
    from src.analysis.market_microstructure import MarketMicrostructureAnalyzer
    from src.optimization.advanced_portfolio import AdvancedPortfolioOptimizer
    from src.core.market_regime import MarketRegimeDetector
    from src.data.historical_updater import HistoricalDataUpdater
    ADVANCED_MODULES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Advanced modules not available: {e}")
    ADVANCED_MODULES_AVAILABLE = False

# Configuration
DB_PATH = 'db/historical_data.db'
OP_DB_PATH = 'db/enhanced_operation.db'
CONFIG_PATH = 'config/enhanced_config.json'
SCHEDULE_TIME = "16:00"  # 24-hr format

class EnhancedTradingSystem:
    """
    Enhanced trading system integrating all advanced modules.
    """
    
    def __init__(self):
        """Initialize the enhanced trading system."""
        self.db_path = DB_PATH
        self.op_db_path = OP_DB_PATH
        
        # Initialize advanced modules
        if ADVANCED_MODULES_AVAILABLE:
            self.signal_generator = AdvancedSignalGenerator(DB_PATH)
            self.microstructure_analyzer = MarketMicrostructureAnalyzer(DB_PATH)
            self.portfolio_optimizer = AdvancedPortfolioOptimizer(DB_PATH)
            self.regime_detector = MarketRegimeDetector(DB_PATH)
            self.data_updater = HistoricalDataUpdater(DB_PATH)
        else:
            logger.error("Advanced modules not available. System will not function properly.")
            return
        
        # Load configuration
        self.config = self._load_config()
        
        # Performance tracking
        self.performance_history = []
        self.signal_history = []
        
        # Initialize operation database
        self._init_operation_db()
        
        logger.info("Enhanced Trading System initialized successfully")
    
    def _load_config(self) -> Dict:
        """Load configuration from JSON file."""
        default_config = {
            'symbols': ['BBCA', 'TLKM', 'ASII', 'UNVR', 'ICBP'],
            'ml_confidence_threshold': 0.6,
            'microstructure_weight': 0.3,
            'optimization_method': 'regime_dependent',
            'rebalancing_frequency': 'daily',
            'risk_management': {
                'max_drawdown': 0.15,
                'position_limit': 0.25,
                'stop_loss': 0.05
            },
            'performance_metrics': {
                'target_sharpe': 1.5,
                'target_sortino': 2.0,
                'max_volatility': 0.20
            }
        }
        
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                # Merge with defaults
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                # Create default config file
                os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                with open(CONFIG_PATH, 'w') as f:
                    json.dump(default_config, f, indent=2)
                return default_config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return default_config
    
    def _init_operation_db(self):
        """Initialize operation database."""
        try:
            conn = sqlite3.connect(self.op_db_path)
            cursor = conn.cursor()
            
            # Create tables for enhanced operation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS enhanced_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    ml_signal TEXT,
                    ml_confidence REAL,
                    microstructure_signal TEXT,
                    microstructure_confidence REAL,
                    combined_signal TEXT,
                    combined_confidence REAL,
                    regime TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS portfolio_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    allocation REAL,
                    optimization_method TEXT,
                    regime TEXT,
                    performance_metrics TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    total_return REAL,
                    sharpe_ratio REAL,
                    sortino_ratio REAL,
                    max_drawdown REAL,
                    volatility REAL,
                    regime TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Enhanced operation database initialized")
            
        except Exception as e:
            logger.error(f"Error initializing operation database: {e}")
    
    async def update_market_data(self):
        """Update market data asynchronously."""
        try:
            logger.info("Starting market data update...")
            
            # Update data for configured symbols
            symbols = self.config['symbols']
            await self.data_updater.update_all(symbols)
            
            logger.info("Market data update completed")
            
        except Exception as e:
            logger.error(f"Error updating market data: {e}")
    
    def detect_market_regime(self) -> str:
        """Detect current market regime."""
        try:
            regime = self.regime_detector.detect_regime(market_code='indo', lookback=90)
            logger.info(f"Market regime detected: {regime}")
            return regime
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            return "UNKNOWN"
    
    def generate_advanced_signals(self, symbols: List[str], regime: str) -> Dict:
        """
        Generate advanced trading signals using multiple approaches.
        
        Args:
            symbols: List of stock symbols
            regime: Current market regime
            
        Returns:
            Dictionary with signals for each symbol
        """
        signals = {}
        
        for symbol in symbols:
            try:
                symbol_signals = {}
                
                # 1. Machine Learning signals
                ml_signals = self.signal_generator.generate_signals(
                    symbol, 
                    self.config['ml_confidence_threshold']
                )
                symbol_signals['ml'] = ml_signals
                
                # 2. Microstructure signals
                microstructure_signals = self.microstructure_analyzer.generate_microstructure_signals(symbol)
                symbol_signals['microstructure'] = microstructure_signals
                
                # 3. Combine signals
                combined_signal = self._combine_signals(ml_signals, microstructure_signals, regime)
                symbol_signals['combined'] = combined_signal
                
                signals[symbol] = symbol_signals
                
                # Store signals in database
                self._store_signals(symbol, symbol_signals, regime)
                
            except Exception as e:
                logger.error(f"Error generating signals for {symbol}: {e}")
                signals[symbol] = {'error': str(e)}
        
        return signals
    
    def _combine_signals(self, ml_signals: Dict, microstructure_signals: Dict, regime: str) -> Dict:
        """Combine ML and microstructure signals."""
        try:
            # Extract signal strengths
            ml_strength = 0
            microstructure_strength = 0
            
            # ML signal strength
            if 'combined' in ml_signals and 'confidence' in ml_signals['combined']:
                ml_strength = ml_signals['combined']['confidence']
                if ml_signals['combined']['signal'] == 'SELL':
                    ml_strength = -ml_strength
            
            # Microstructure signal strength
            if 'combined_signal' in microstructure_signals and 'confidence' in microstructure_signals['combined_signal']:
                microstructure_strength = microstructure_signals['combined_signal']['confidence']
                if microstructure_signals['combined_signal']['signal'] == 'SELL':
                    microstructure_strength = -microstructure_strength
            
            # Weighted combination
            ml_weight = 1 - self.config['microstructure_weight']
            microstructure_weight = self.config['microstructure_weight']
            
            combined_strength = (
                ml_strength * ml_weight + 
                microstructure_strength * microstructure_weight
            )
            
            # Determine final signal
            if combined_strength > 0.3:
                signal = 'BUY'
                confidence = abs(combined_strength)
            elif combined_strength < -0.3:
                signal = 'SELL'
                confidence = abs(combined_strength)
            else:
                signal = 'HOLD'
                confidence = 0.5
            
            return {
                'signal': signal,
                'confidence': confidence,
                'ml_strength': ml_strength,
                'microstructure_strength': microstructure_strength,
                'combined_strength': combined_strength
            }
            
        except Exception as e:
            logger.error(f"Error combining signals: {e}")
            return {'signal': 'HOLD', 'confidence': 0.5, 'error': str(e)}
    
    def _store_signals(self, symbol: str, signals: Dict, regime: str):
        """Store signals in database."""
        try:
            conn = sqlite3.connect(self.op_db_path)
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            # Extract signal information
            ml_signal = signals.get('ml', {}).get('combined', {}).get('signal', 'HOLD')
            ml_confidence = signals.get('ml', {}).get('combined', {}).get('confidence', 0.5)
            
            microstructure_signal = signals.get('microstructure', {}).get('combined_signal', {}).get('signal', 'HOLD')
            microstructure_confidence = signals.get('microstructure', {}).get('combined_signal', {}).get('confidence', 0.5)
            
            combined_signal = signals.get('combined', {}).get('signal', 'HOLD')
            combined_confidence = signals.get('combined', {}).get('confidence', 0.5)
            
            cursor.execute('''
                INSERT INTO enhanced_signals 
                (timestamp, symbol, ml_signal, ml_confidence, microstructure_signal, 
                 microstructure_confidence, combined_signal, combined_confidence, regime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, ml_signal, ml_confidence, microstructure_signal,
                  microstructure_confidence, combined_signal, combined_confidence, regime))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing signals: {e}")
    
    def optimize_portfolio(self, signals: Dict, regime: str) -> Dict:
        """
        Optimize portfolio using advanced techniques.
        
        Args:
            signals: Dictionary with signals for each symbol
            regime: Current market regime
            
        Returns:
            Dictionary with optimized portfolio
        """
        try:
            # Filter symbols with positive signals
            positive_signals = {
                symbol: signal_data for symbol, signal_data in signals.items()
                if signal_data.get('combined', {}).get('signal') == 'BUY'
            }
            
            if not positive_signals:
                logger.warning("No positive signals found for portfolio optimization")
                return {}
            
            symbols = list(positive_signals.keys())
            
            # Get optimization method from config
            method = self.config['optimization_method']
            
            # Run optimization
            if method == 'regime_dependent':
                result = self.portfolio_optimizer.regime_dependent_optimization(
                    self.portfolio_optimizer.get_returns_data(symbols), regime
                )
            elif method == 'risk_parity':
                result = self.portfolio_optimizer.risk_parity_optimization(
                    self.portfolio_optimizer.get_returns_data(symbols)
                )
            elif method == 'hierarchical_risk_parity':
                result = self.portfolio_optimizer.hierarchical_risk_parity(
                    self.portfolio_optimizer.get_returns_data(symbols)
                )
            elif method == 'kelly_criterion':
                result = self.portfolio_optimizer.kelly_criterion_optimization(
                    self.portfolio_optimizer.get_returns_data(symbols)
                )
            else:
                # Default to regime-dependent
                result = self.portfolio_optimizer.regime_dependent_optimization(
                    self.portfolio_optimizer.get_returns_data(symbols), regime
                )
            
            if 'error' not in result:
                # Store portfolio allocation
                self._store_portfolio_allocation(result, method, regime)
                
                # Add signal confidence to weights
                for symbol in result['weights']:
                    if symbol in positive_signals:
                        signal_confidence = positive_signals[symbol]['combined']['confidence']
                        result['weights'][symbol] *= signal_confidence
                
                # Renormalize weights
                total_weight = sum(result['weights'].values())
                if total_weight > 0:
                    result['weights'] = {k: v/total_weight for k, v in result['weights'].items()}
            
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing portfolio: {e}")
            return {'error': str(e)}
    
    def _store_portfolio_allocation(self, result: Dict, method: str, regime: str):
        """Store portfolio allocation in database."""
        try:
            conn = sqlite3.connect(self.op_db_path)
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            for symbol, allocation in result['weights'].items():
                performance_metrics = json.dumps(result.get('portfolio_metrics', {}))
                
                cursor.execute('''
                    INSERT INTO portfolio_allocations 
                    (timestamp, symbol, allocation, optimization_method, regime, performance_metrics)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (timestamp, symbol, allocation, method, regime, performance_metrics))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing portfolio allocation: {e}")
    
    def calculate_performance_metrics(self, portfolio_result: Dict) -> Dict:
        """Calculate and store performance metrics."""
        try:
            if 'portfolio_metrics' not in portfolio_result:
                return {}
            
            metrics = portfolio_result['portfolio_metrics']
            
            # Store performance metrics
            conn = sqlite3.connect(self.op_db_path)
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO performance_tracking 
                (timestamp, total_return, sharpe_ratio, sortino_ratio, max_drawdown, volatility, regime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                metrics.get('annualized_return', 0),
                metrics.get('sharpe_ratio', 0),
                metrics.get('sortino_ratio', 0),
                metrics.get('max_drawdown', 0),
                metrics.get('annualized_volatility', 0),
                'UNKNOWN'  # Will be updated with actual regime
            ))
            
            conn.commit()
            conn.close()
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {}
    
    def generate_enhanced_report(self, signals: Dict, portfolio_result: Dict, 
                               regime: str, performance_metrics: Dict) -> str:
        """Generate comprehensive operation report."""
        try:
            report = f"""
=== Enhanced Trading System Report ===
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Market Regime: {regime}

SIGNAL ANALYSIS:
"""
            
            # Signal summary
            buy_signals = 0
            sell_signals = 0
            hold_signals = 0
            
            for symbol, signal_data in signals.items():
                if 'combined' in signal_data:
                    signal = signal_data['combined']['signal']
                    confidence = signal_data['combined']['confidence']
                    
                    if signal == 'BUY':
                        buy_signals += 1
                    elif signal == 'SELL':
                        sell_signals += 1
                    else:
                        hold_signals += 1
                    
                    report += f"  {symbol}: {signal} (Confidence: {confidence:.2f})\n"
            
            report += f"""
Signal Summary:
  BUY: {buy_signals}
  SELL: {sell_signals}
  HOLD: {hold_signals}

PORTFOLIO OPTIMIZATION:
Method: {self.config['optimization_method']}
"""
            
            if 'weights' in portfolio_result:
                report += "Allocations:\n"
                for symbol, weight in portfolio_result['weights'].items():
                    report += f"  {symbol}: {weight:.2%}\n"
            
            if performance_metrics:
                report += f"""
PERFORMANCE METRICS:
  Annualized Return: {performance_metrics.get('annualized_return', 0):.2%}
  Sharpe Ratio: {performance_metrics.get('sharpe_ratio', 0):.2f}
  Sortino Ratio: {performance_metrics.get('sortino_ratio', 0):.2f}
  Max Drawdown: {performance_metrics.get('max_drawdown', 0):.2%}
  Volatility: {performance_metrics.get('annualized_volatility', 0):.2%}
  Diversification Ratio: {performance_metrics.get('diversification_ratio', 0):.2f}
"""
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"Error generating report: {str(e)}"
    
    async def run_enhanced_operation(self):
        """Run the complete enhanced operation."""
        try:
            logger.info("=== Starting Enhanced Trading Operation ===")
            
            # 1. Update market data
            await self.update_market_data()
            
            # 2. Detect market regime
            regime = self.detect_market_regime()
            
            # 3. Generate advanced signals
            symbols = self.config['symbols']
            signals = self.generate_advanced_signals(symbols, regime)
            
            # 4. Optimize portfolio
            portfolio_result = self.optimize_portfolio(signals, regime)
            
            # 5. Calculate performance metrics
            performance_metrics = self.calculate_performance_metrics(portfolio_result)
            
            # 6. Generate report
            report = self.generate_enhanced_report(signals, portfolio_result, regime, performance_metrics)
            
            # 7. Log results
            logger.info("Enhanced operation completed successfully")
            logger.info(report)
            
            # 8. Store operation summary
            self._store_operation_summary(signals, portfolio_result, regime, performance_metrics)
            
            return {
                'signals': signals,
                'portfolio_result': portfolio_result,
                'regime': regime,
                'performance_metrics': performance_metrics,
                'report': report
            }
            
        except Exception as e:
            logger.error(f"Error in enhanced operation: {e}")
            return {'error': str(e)}
    
    def _store_operation_summary(self, signals: Dict, portfolio_result: Dict, 
                               regime: str, performance_metrics: Dict):
        """Store operation summary for historical tracking."""
        try:
            summary = {
                'timestamp': datetime.now().isoformat(),
                'regime': regime,
                'signals_count': len(signals),
                'portfolio_method': self.config['optimization_method'],
                'performance_metrics': performance_metrics,
                'success': 'error' not in portfolio_result
            }
            
            # Store in a summary file
            summary_file = f"logs/operation_summary_{datetime.now().strftime('%Y%m%d')}.json"
            os.makedirs(os.path.dirname(summary_file), exist_ok=True)
            
            with open(summary_file, 'a') as f:
                f.write(json.dumps(summary) + '\n')
                
        except Exception as e:
            logger.error(f"Error storing operation summary: {e}")

async def main():
    """Main function for enhanced operation."""
    try:
        # Initialize enhanced trading system
        trading_system = EnhancedTradingSystem()
        
        if not ADVANCED_MODULES_AVAILABLE:
            logger.error("Advanced modules not available. Cannot run enhanced operation.")
            return
        
        # Run enhanced operation
        result = await trading_system.run_enhanced_operation()
        
        if 'error' in result:
            logger.error(f"Operation failed: {result['error']}")
        else:
            logger.info("Enhanced operation completed successfully")
            
    except Exception as e:
        logger.error(f"Error in main function: {e}")

if __name__ == "__main__":
    asyncio.run(main())
