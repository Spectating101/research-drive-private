#!/usr/bin/env python3
# Filename: src/core/causal_inference.py
"""
Causal Inference Framework Module

This module provides causal analysis tools for trading strategies:
1. Synthetic control methods for counterfactual analysis
2. Causal impact assessment of strategy signals
3. Treatment effect estimation for trading decisions
4. Natural experiment analysis for strategy validation

These methods help distinguish true causal effects from spurious correlations,
providing a more robust framework for strategy validation.
"""

import numpy as np
import pandas as pd
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union, Optional, Any, Callable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import statistical packages for causal inference
try:
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.stats.diagnostic import acorr_ljungbox
    import statsmodels.api as sm
    STATSMODELS_AVAILABLE = True
    logger.info("statsmodels available for time series analysis")
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available. Some causal inference methods will be limited.")

# Try to import more specialized causal inference libraries
try:
    import causalimpact
    CAUSALIMPACT_AVAILABLE = True
    logger.info("CausalImpact package available for Bayesian causal analysis")
except ImportError:
    CAUSALIMPACT_AVAILABLE = False
    logger.warning("CausalImpact package not available. Using alternative methods.")

# Try to import matching and propensity score methods
try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import NearestNeighbors
    from sklearn.linear_model import LogisticRegression
    MATCHING_AVAILABLE = True
    logger.info("scikit-learn available for matching methods")
except ImportError:
    MATCHING_AVAILABLE = False
    logger.warning("scikit-learn not available. Matching methods will be limited.")

class CausalInferenceFramework:
    """
    Framework for causal inference analysis of trading strategies.
    """
    
    def __init__(self, output_dir: str = "data/causal_analysis"):
        """
        Initialize the causal inference framework.
        
        Args:
            output_dir: Directory for saving analysis results
        """
        self.output_dir = output_dir
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Track analysis results
        self.analysis_results = {}
        
    def causal_strategy_validation(self, 
                                 strategy_data: pd.DataFrame, 
                                 signal_dates: List[datetime], 
                                 signal_types: Optional[List[str]] = None,
                                 pre_period: int = 20, 
                                 post_period: int = 20,
                                 control_variables: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Validate strategy performance using synthetic control methods.
        
        Args:
            strategy_data: DataFrame with price and return data
            signal_dates: List of signal dates (interventions)
            signal_types: List of signal types (e.g., 'buy', 'sell')
            pre_period: Days before signal for pre-intervention period
            post_period: Days after signal for post-intervention period
            control_variables: Variables to use as controls
            
        Returns:
            dict: Causal analysis results
        """
        if not STATSMODELS_AVAILABLE:
            logger.error("statsmodels required for causal strategy validation")
            return {"error": "statsmodels not available"}
            
        # Ensure strategy_data has datetime index
        if not isinstance(strategy_data.index, pd.DatetimeIndex):
            logger.error("strategy_data must have DatetimeIndex")
            return {"error": "Invalid data format"}
            
        # If no signal types provided, default to 'signal'
        if signal_types is None:
            signal_types = ['signal'] * len(signal_dates)
            
        if len(signal_dates) != len(signal_types):
            logger.error("signal_dates and signal_types must have same length")
            return {"error": "Mismatched signal dates and types"}
            
        # Initialize results
        results = {
            'overall': {
                'num_signals': len(signal_dates),
                'avg_treatment_effect': 0.0,
                'significant_signals': 0,
                'signal_types': {}
            },
            'signals': []
        }
        
        # Process each signal
        for i, (signal_date, signal_type) in enumerate(zip(signal_dates, signal_types)):
            logger.info(f"Analyzing signal {i+1}/{len(signal_dates)}: {signal_date} ({signal_type})")
            
            try:
                # Find closest date in data if exact match not found
                if signal_date not in strategy_data.index:
                    closest_date = strategy_data.index[strategy_data.index.get_indexer([signal_date], method='nearest')[0]]
                    logger.warning(f"Signal date {signal_date} not found, using closest date {closest_date}")
                    signal_date = closest_date
                
                # Get signal index
                signal_idx = strategy_data.index.get_loc(signal_date)
                
                # Define pre and post periods
                pre_start = max(0, signal_idx - pre_period)
                pre_end = signal_idx
                post_start = signal_idx + 1
                post_end = min(len(strategy_data), signal_idx + post_period + 1)
                
                # Get data for periods
                pre_data = strategy_data.iloc[pre_start:pre_end]
                post_data = strategy_data.iloc[post_start:post_end]
                
                # If either period is empty, skip this signal
                if len(pre_data) == 0 or len(post_data) == 0:
                    logger.warning(f"Insufficient data for signal on {signal_date}")
                    continue
                
                # Perform causal analysis based on available methods
                if CAUSALIMPACT_AVAILABLE and control_variables is not None:
                    # Use CausalImpact for Bayesian structural time series analysis
                    signal_result = self._analyze_with_causalimpact(
                        strategy_data, signal_date, pre_period, post_period, control_variables)
                else:
                    # Use simpler DID (Difference-in-Differences) approach
                    signal_result = self._analyze_with_did(
                        strategy_data, signal_date, pre_period, post_period, control_variables)
                
                # Add signal type and date to result
                signal_result['signal_date'] = signal_date
                signal_result['signal_type'] = signal_type
                
                # Add to results
                results['signals'].append(signal_result)
                
                # Update aggregate statistics
                results['overall']['avg_treatment_effect'] += signal_result['avg_effect']
                if signal_result['significant']:
                    results['overall']['significant_signals'] += 1
                
                # Update by signal type
                if signal_type not in results['overall']['signal_types']:
                    results['overall']['signal_types'][signal_type] = {
                        'count': 0,
                        'avg_effect': 0.0,
                        'significant': 0
                    }
                
                type_stats = results['overall']['signal_types'][signal_type]
                type_stats['count'] += 1
                type_stats['avg_effect'] += signal_result['avg_effect']
                if signal_result['significant']:
                    type_stats['significant'] += 1
                
            except Exception as e:
                logger.error(f"Error analyzing signal on {signal_date}: {e}")
                continue
        
        # Calculate final aggregate statistics
        if results['signals']:
            results['overall']['avg_treatment_effect'] /= len(results['signals'])
            
            # Calculate by signal type
            for signal_type, stats in results['overall']['signal_types'].items():
                if stats['count'] > 0:
                    stats['avg_effect'] /= stats['count']
        
        # Store analysis results
        analysis_id = f"strategy_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.analysis_results[analysis_id] = results
        
        return results
    
    def _analyze_with_causalimpact(self, 
                                 data: pd.DataFrame, 
                                 intervention_date: datetime,
                                 pre_period: int = 20, 
                                 post_period: int = 20,
                                 control_variables: List[str] = None) -> Dict[str, Any]:
        """
        Analyze causal impact using Bayesian structural time series.
        
        Args:
            data: DataFrame with price and return data
            intervention_date: Date of intervention
            pre_period: Days before signal for pre-intervention period
            post_period: Days after signal for post-intervention period
            control_variables: Variables to use as controls
            
        Returns:
            dict: Causal analysis result
        """
        # Get intervention index
        intervention_idx = data.index.get_loc(intervention_date)
        
        # Define pre and post periods
        pre_start = max(0, intervention_idx - pre_period)
        pre_end = intervention_idx
        post_start = intervention_idx + 1
        post_end = min(len(data), intervention_idx + post_period + 1)
        
        # Get data for periods
        pre_data = data.iloc[pre_start:pre_end]
        post_data = data.iloc[post_start:post_end]
        
        # Prepare data for CausalImpact
        if 'return' in data.columns:
            target = 'return'
        elif 'close' in data.columns:
            target = 'close'
        else:
            # Use first numeric column
            numeric_cols = data.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                target = numeric_cols[0]
            else:
                raise ValueError("No numeric columns found in data")
        
        # Select control variables
        if control_variables is None:
            # Use all numeric columns except target as controls
            control_variables = [col for col in data.select_dtypes(include=[np.number]).columns 
                               if col != target]
        
        # Prepare data for CausalImpact
        ci_data = data[[target] + control_variables].copy()
        
        # Define pre/post periods in required format
        pre_period = [pre_start, pre_end - 1]  # CausalImpact uses zero-indexed periods
        post_period = [post_start, post_end - 1]
        
        # Run CausalImpact analysis
        try:
            ci = causalimpact.CausalImpact(ci_data, pre_period, post_period)
            summary = ci.summary()
            report = ci.summary(output='report')
            
            # Extract key statistics
            avg_effect = ci.summary_data.iloc[0]['abs_effect']
            rel_effect = ci.summary_data.iloc[0]['rel_effect']
            p_value = ci.summary_data.iloc[0]['p']
            significant = p_value < 0.05
            
            # Calculate daily effects
            point_effects = ci.inferences['point_effects']
            cumulative_effects = ci.inferences['post_cum_effects']
            
            result = {
                'method': 'causalimpact',
                'avg_effect': float(avg_effect),
                'rel_effect': float(rel_effect),
                'p_value': float(p_value),
                'significant': significant,
                'daily_effects': point_effects.tolist() if hasattr(point_effects, 'tolist') else list(point_effects),
                'cumulative_effects': cumulative_effects.tolist() if hasattr(cumulative_effects, 'tolist') else list(cumulative_effects),
                'summary': summary
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error in CausalImpact analysis: {e}")
            # Fall back to DID if CausalImpact fails
            return self._analyze_with_did(
                data, intervention_date, pre_period, post_period, control_variables)
    
    def _analyze_with_did(self, 
                        data: pd.DataFrame, 
                        intervention_date: datetime,
                        pre_period: int = 20, 
                        post_period: int = 20,
                        control_variables: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Analyze causal impact using difference-in-differences approach.
        
        Args:
            data: DataFrame with price and return data
            intervention_date: Date of intervention
            pre_period: Days before signal for pre-intervention period
            post_period: Days after signal for post-intervention period
            control_variables: Variables to use as controls
            
        Returns:
            dict: Causal analysis result
        """
        # Get intervention index
        intervention_idx = data.index.get_loc(intervention_date)
        
        # Define pre and post periods
        pre_start = max(0, intervention_idx - pre_period)
        pre_end = intervention_idx
        post_start = intervention_idx + 1
        post_end = min(len(data), intervention_idx + post_period + 1)
        
        # Get data for periods
        pre_data = data.iloc[pre_start:pre_end]
        post_data = data.iloc[post_start:post_end]
        
        # Determine target variable
        if 'return' in data.columns:
            target = 'return'
        elif 'close' in data.columns:
            target = 'close'
        else:
            # Use first numeric column
            numeric_cols = data.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                target = numeric_cols[0]
            else:
                raise ValueError("No numeric columns found in data")
        
        # Calculate pre and post averages
        pre_avg = pre_data[target].mean()
        post_avg = post_data[target].mean()
        
        # Calculate simple difference
        simple_diff = post_avg - pre_avg
        
        # Calculate more sophisticated DID if control variables are available
        if control_variables and STATSMODELS_AVAILABLE:
            # Prepare data for regression
            regression_data = data.iloc[pre_start:post_end].copy()
            
            # Create treatment dummy (1 for post-intervention)
            regression_data['post_intervention'] = 0
            regression_data.iloc[pre_end-pre_start+1:, regression_data.columns.get_loc('post_intervention')] = 1
            
            # Create control dummies if needed
            if control_variables:
                # For now, just use the controls directly
                X = regression_data[control_variables + ['post_intervention']]
            else:
                X = regression_data[['post_intervention']]
                
            # Add constant
            X = sm.add_constant(X)
            
            # Run regression
            model = sm.OLS(regression_data[target], X)
            results = model.fit()
            
            # Extract treatment effect and p-value
            treatment_idx = results.params.index.get_loc('post_intervention')
            did_effect = results.params.iloc[treatment_idx]
            p_value = results.pvalues.iloc[treatment_idx]
            
            # Calculate daily effects and cumulative effects
            daily_effects = np.ones(len(post_data)) * did_effect
            cumulative_effects = np.cumsum(daily_effects)
            
            significant = p_value < 0.05
            
        else:
            # Without controls, use simple difference
            did_effect = simple_diff
            
            # Estimate statistical significance using t-test
            if STATSMODELS_AVAILABLE:
                from scipy import stats
                t_stat, p_value = stats.ttest_ind(pre_data[target], post_data[target])
                significant = p_value < 0.05
            else:
                # Can't calculate significance without statsmodels
                p_value = None
                significant = False
                
            # Simple daily and cumulative effects
            daily_effects = np.ones(len(post_data)) * did_effect
            cumulative_effects = np.cumsum(daily_effects)
        
        # Prepare result
        result = {
            'method': 'did',
            'avg_effect': float(did_effect),
            'simple_diff': float(simple_diff),
            'rel_effect': float(did_effect / pre_avg) if pre_avg != 0 else float('inf'),
            'p_value': float(p_value) if p_value is not None else None,
            'significant': significant,
            'pre_avg': float(pre_avg),
            'post_avg': float(post_avg),
            'daily_effects': daily_effects.tolist(),
            'cumulative_effects': cumulative_effects.tolist(),
        }
        
        return result
    
    def matching_analysis(self, 
                        treatment_data: pd.DataFrame, 
                        control_pool: pd.DataFrame,
                        treatment_dates: Dict[str, datetime],
                        matching_variables: List[str],
                        outcome_variable: str,
                        pre_period: int = 20,
                        post_period: int = 20,
                        matching_method: str = 'nearest') -> Dict[str, Any]:
        """
        Perform matching analysis to estimate treatment effects.
        
        Args:
            treatment_data: DataFrame with treatment group data
            control_pool: DataFrame with potential control group data
            treatment_dates: Dictionary mapping treatment IDs to treatment dates
            matching_variables: Variables to use for matching
            outcome_variable: Variable to measure treatment effect on
            pre_period: Days before treatment for pre-treatment period
            post_period: Days after treatment for post-treatment period
            matching_method: Method for matching ('nearest', 'propensity', 'mahalanobis')
            
        Returns:
            dict: Matching analysis results
        """
        if not MATCHING_AVAILABLE:
            logger.error("scikit-learn required for matching analysis")
            return {"error": "scikit-learn not available"}
            
        # Ensure DataFrames have datetime indices
        if not isinstance(treatment_data.index, pd.DatetimeIndex) or not isinstance(control_pool.index, pd.DatetimeIndex):
            logger.error("DataFrames must have DatetimeIndex")
            return {"error": "Invalid data format"}
            
        # Check that all required variables are in the data
        for var in matching_variables + [outcome_variable]:
            if var not in treatment_data.columns or var not in control_pool.columns:
                logger.error(f"Variable {var} not found in data")
                return {"error": f"Variable {var} not found in data"}
                
        # Initialize results
        results = {
            'overall': {
                'num_treatments': len(treatment_dates),
                'avg_treatment_effect': 0.0,
                'significant_treatments': 0
            },
            'treatments': []
        }
        
        # Process each treatment
        for treatment_id, treatment_date in treatment_dates.items():
            logger.info(f"Analyzing treatment {treatment_id} on {treatment_date}")
            
            try:
                # Find treatment date in data
                if treatment_date not in treatment_data.index:
                    closest_date = treatment_data.index[treatment_data.index.get_indexer([treatment_date], method='nearest')[0]]
                    logger.warning(f"Treatment date {treatment_date} not found, using closest date {closest_date}")
                    treatment_date = closest_date
                
                # Get treatment index
                treatment_idx = treatment_data.index.get_loc(treatment_date)
                
                # Define pre and post periods
                pre_start = max(0, treatment_idx - pre_period)
                pre_end = treatment_idx
                post_start = treatment_idx + 1
                post_end = min(len(treatment_data), treatment_idx + post_period + 1)
                
                # Get data for periods
                pre_data = treatment_data.iloc[pre_start:pre_end]
                post_data = treatment_data.iloc[post_start:post_end]
                
                # If either period is empty, skip this treatment
                if len(pre_data) == 0 or len(post_data) == 0:
                    logger.warning(f"Insufficient data for treatment {treatment_id}")
                    continue
                
                # Calculate treatment outcome
                pre_outcome = pre_data[outcome_variable].mean()
                post_outcome = post_data[outcome_variable].mean()
                treatment_effect = post_outcome - pre_outcome
                
                # Perform matching based on method
                if matching_method == 'nearest':
                    matched_effect = self._nearest_neighbor_matching(
                        treatment_data, control_pool, treatment_date,
                        matching_variables, outcome_variable, pre_period, post_period)
                elif matching_method == 'propensity':
                    matched_effect = self._propensity_score_matching(
                        treatment_data, control_pool, treatment_date,
                        matching_variables, outcome_variable, pre_period, post_period)
                else:
                    matched_effect = self._mahalanobis_matching(
                        treatment_data, control_pool, treatment_date,
                        matching_variables, outcome_variable, pre_period, post_period)
                
                # Calculate average treatment effect on the treated (ATT)
                att = treatment_effect - matched_effect
                
                # Calculate statistical significance
                if STATSMODELS_AVAILABLE:
                    from scipy import stats
                    
                    # Compare post-treatment outcomes with matched control outcomes
                    post_treatment = post_data[outcome_variable].values
                    
                    # Calculate matched control outcomes
                    # Note: In a real implementation, we would have the actual matched control data
                    # Here we approximate by using the pre-treatment mean plus the matched effect
                    matched_control = pre_outcome + matched_effect
                    
                    # Simple t-test for significance
                    t_stat, p_value = stats.ttest_1samp(post_treatment, matched_control)
                    significant = p_value < 0.05
                else:
                    t_stat = None
                    p_value = None
                    significant = None
                
                # Prepare treatment result
                treatment_result = {
                    'treatment_id': treatment_id,
                    'treatment_date': treatment_date,
                    'pre_outcome': float(pre_outcome),
                    'post_outcome': float(post_outcome),
                    'treatment_effect': float(treatment_effect),
                    'matched_effect': float(matched_effect),
                    'att': float(att),
                    't_stat': float(t_stat) if t_stat is not None else None,
                    'p_value': float(p_value) if p_value is not None else None,
                    'significant': significant
                }
                
                # Add to results
                results['treatments'].append(treatment_result)
                
                # Update aggregate statistics
                results['overall']['avg_treatment_effect'] += att
                if significant:
                    results['overall']['significant_treatments'] += 1
                
            except Exception as e:
                logger.error(f"Error analyzing treatment {treatment_id}: {e}")
                continue
        
        # Calculate final aggregate statistics
        if results['treatments']:
            results['overall']['avg_treatment_effect'] /= len(results['treatments'])
        
        # Store analysis results
        analysis_id = f"matching_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.analysis_results[analysis_id] = results
        
        return results
    
    def _nearest_neighbor_matching(self,
                                treatment_data: pd.DataFrame,
                                control_pool: pd.DataFrame,
                                treatment_date: datetime,
                                matching_variables: List[str],
                                outcome_variable: str,
                                pre_period: int = 20,
                                post_period: int = 20,
                                n_neighbors: int = 5) -> float:
        """
        Perform nearest neighbor matching.
        
        Args:
            treatment_data: DataFrame with treatment group data
            control_pool: DataFrame with potential control group data
            treatment_date: Treatment date
            matching_variables: Variables to use for matching
            outcome_variable: Variable to measure treatment effect on
            pre_period: Days before treatment for pre-treatment period
            post_period: Days after treatment for post-treatment period
            n_neighbors: Number of nearest neighbors to match
            
        Returns:
            float: Matched control effect
        """
        # Get treatment index
        treatment_idx = treatment_data.index.get_loc(treatment_date)
        
        # Define pre and post periods
        pre_start = max(0, treatment_idx - pre_period)
        pre_end = treatment_idx
        post_start = treatment_idx + 1
        post_end = min(len(treatment_data), treatment_idx + post_period + 1)
        
        # Get pre-treatment data for matching
        pre_treatment = treatment_data.iloc[pre_start:pre_end][matching_variables].mean().values.reshape(1, -1)
        
        # Get all control pre-treatment data
        # For simplicity, we'll use the same pre_period for all controls
        control_pre_means = []
        control_post_outcomes = []
        
        for i in range(len(control_pool) - post_period):
            # Define control pre and post periods
            control_pre_start = i
            control_pre_end = i + pre_period
            control_post_start = control_pre_end
            control_post_end = control_post_start + post_period
            
            # Skip if not enough data
            if control_post_end >= len(control_pool):
                continue
                
            # Get control pre and post data
            control_pre = control_pool.iloc[control_pre_start:control_pre_end]
            control_post = control_pool.iloc[control_post_start:control_post_end]
            
            # Calculate pre means for matching
            control_pre_mean = control_pre[matching_variables].mean().values
            control_pre_means.append(control_pre_mean)
            
            # Calculate post outcome for effect estimation
            control_post_outcome = control_post[outcome_variable].mean()
            control_post_outcomes.append(control_post_outcome)
        
        if not control_pre_means:
            logger.warning("No control periods found for matching")
            return 0.0
            
        # Convert to arrays
        control_pre_means = np.array(control_pre_means)
        control_post_outcomes = np.array(control_post_outcomes)
        
        # Standardize features
        scaler = StandardScaler()
        scaled_treatment = scaler.fit_transform(pre_treatment)
        scaled_controls = scaler.transform(control_pre_means)
        
        # Find nearest neighbors
        nbrs = NearestNeighbors(n_neighbors=min(n_neighbors, len(scaled_controls)))
        nbrs.fit(scaled_controls)
        distances, indices = nbrs.kneighbors(scaled_treatment)
        
        # Calculate matched control effect
        if len(indices) > 0 and len(indices[0]) > 0:
            matched_outcomes = control_post_outcomes[indices[0]]
            matched_effect = np.mean(matched_outcomes) - np.mean(control_pre_means[indices[0], :])
            return matched_effect
        else:
            logger.warning("No matches found")
            return 0.0
    
    def _propensity_score_matching(self,
                                treatment_data: pd.DataFrame,
                                control_pool: pd.DataFrame,
                                treatment_date: datetime,
                                matching_variables: List[str],
                                outcome_variable: str,
                                pre_period: int = 20,
                                post_period: int = 20) -> float:
        """
        Perform propensity score matching.
        
        Args:
            treatment_data: DataFrame with treatment group data
            control_pool: DataFrame with potential control group data
            treatment_date: Treatment date
            matching_variables: Variables to use for matching
            outcome_variable: Variable to measure treatment effect on
            pre_period: Days before treatment for pre-treatment period
            post_period: Days after treatment for post-treatment period
            
        Returns:
            float: Matched control effect
        """
        # This implementation is simplified and would need more sophisticated approaches
        # for real-world applications, including proper propensity score modeling.
        # For now, we'll use a simplified approach similar to nearest neighbor matching.
        
        # Get treatment index
        treatment_idx = treatment_data.index.get_loc(treatment_date)
        
        # Define pre and post periods
        pre_start = max(0, treatment_idx - pre_period)
        pre_end = treatment_idx
        post_start = treatment_idx + 1
        post_end = min(len(treatment_data), treatment_idx + post_period + 1)
        
        # Get pre-treatment data
        pre_treatment = treatment_data.iloc[pre_start:pre_end][matching_variables]
        
        # Create synthetic dataset for propensity score estimation
        # Combine treatment and control features
        features = []
        labels = []
        
        # Add treatment data
        features.append(pre_treatment.mean().values)
        labels.append(1)
        
        # Add control data
        for i in range(len(control_pool) - post_period):
            # Define control pre period
            control_pre_start = i
            control_pre_end = i + pre_period
            
            # Skip if not enough data
            if control_pre_end >= len(control_pool):
                continue
                
            # Get control pre data
            control_pre = control_pool.iloc[control_pre_start:control_pre_end]
            
            # Calculate pre means for matching
            control_pre_mean = control_pre[matching_variables].mean().values
            features.append(control_pre_mean)
            labels.append(0)
        
        if len(features) <= 1:
            logger.warning("Not enough control periods for propensity score matching")
            return 0.0
            
        # Convert to arrays
        features = np.array(features)
        labels = np.array(labels)
        
        # Standardize features
        scaler = StandardScaler()
        features = scaler.fit_transform(features)
        
        # Estimate propensity scores
        logistic = LogisticRegression(max_iter=1000)
        logistic.fit(features, labels)
        propensity_scores = logistic.predict_proba(features)[:, 1]
        
        # Find closest matches based on propensity score
        treatment_ps = propensity_scores[0]
        control_ps = propensity_scores[1:]
        
        # Calculate absolute differences
        ps_diff = np.abs(control_ps - treatment_ps)
        
        # Get indices of the 5 closest matches
        n_matches = min(5, len(control_ps))
        match_indices = np.argsort(ps_diff)[:n_matches]
        
        # Calculate matched control effect
        matched_effects = []
        
        for idx in match_indices:
            # Get control index
            control_idx = idx + 1  # Adjust for 0-based indexing and skipping treatment
            
            # Define control pre and post periods
            control_pre_start = control_idx
            control_pre_end = control_pre_start + pre_period
            control_post_start = control_pre_end
            control_post_end = control_post_start + post_period
            
            # Skip if not enough data
            if control_post_end >= len(control_pool):
                continue
                
            # Get control pre and post data
            control_pre = control_pool.iloc[control_pre_start:control_pre_end]
            control_post = control_pool.iloc[control_post_start:control_post_end]
            
            # Calculate effect
            control_pre_outcome = control_pre[outcome_variable].mean()
            control_post_outcome = control_post[outcome_variable].mean()
            matched_effects.append(control_post_outcome - control_pre_outcome)
            
        if not matched_effects:
            logger.warning("No valid matched controls found")
            return 0.0
            
        # Return average matched effect
        return np.mean(matched_effects)
    
    def _mahalanobis_matching(self,
                           treatment_data: pd.DataFrame,
                           control_pool: pd.DataFrame,
                           treatment_date: datetime,
                           matching_variables: List[str],
                           outcome_variable: str,
                           pre_period: int = 20,
                           post_period: int = 20) -> float:
        """
        Perform Mahalanobis distance matching.
        
        Args:
            treatment_data: DataFrame with treatment group data
            control_pool: DataFrame with potential control group data
            treatment_date: Treatment date
            matching_variables: Variables to use for matching
            outcome_variable: Variable to measure treatment effect on
            pre_period: Days before treatment for pre-treatment period
            post_period: Days after treatment for post-treatment period
            
        Returns:
            float: Matched control effect
        """
        # Get treatment index
        treatment_idx = treatment_data.index.get_loc(treatment_date)
        
        # Define pre and post periods
        pre_start = max(0, treatment_idx - pre_period)
        pre_end = treatment_idx
        post_start = treatment_idx + 1
        post_end = min(len(treatment_data), treatment_idx + post_period + 1)
        
        # Get pre-treatment data for matching
        pre_treatment = treatment_data.iloc[pre_start:pre_end][matching_variables].mean().values.reshape(1, -1)
        
        # Get all control pre-treatment data
        control_pre_means = []
        control_post_outcomes = []
        control_pre_outcomes = []
        
        for i in range(len(control_pool) - post_period):
            # Define control pre and post periods
            control_pre_start = i
            control_pre_end = i + pre_period
            control_post_start = control_pre_end
            control_post_end = control_post_start + post_period
            
            # Skip if not enough data
            if control_post_end >= len(control_pool):
                continue
                
            # Get control pre and post data
            control_pre = control_pool.iloc[control_pre_start:control_pre_end]
            control_post = control_pool.iloc[control_post_start:control_post_end]
            
            # Calculate pre means for matching
            control_pre_mean = control_pre[matching_variables].mean().values
            control_pre_means.append(control_pre_mean)
            
            # Calculate pre and post outcomes for effect estimation
            control_pre_outcome = control_pre[outcome_variable].mean()
            control_pre_outcomes.append(control_pre_outcome)
            
            control_post_outcome = control_post[outcome_variable].mean()
            control_post_outcomes.append(control_post_outcome)
            
        if not control_pre_means:
            logger.warning("No control periods found for matching")
            return 0.0
            
        # Convert to arrays
        control_pre_means = np.array(control_pre_means)
        control_pre_outcomes = np.array(control_pre_outcomes)
        control_post_outcomes = np.array(control_post_outcomes)
        
        # Calculate covariance matrix
        cov_matrix = np.cov(control_pre_means, rowvar=False)
        
        # Handle singular covariance matrix
        if np.linalg.matrix_rank(cov_matrix) < len(matching_variables):
            # Add small regularization
            cov_matrix = cov_matrix + np.eye(cov_matrix.shape[0]) * 1e-6
            
        # Calculate inverse covariance matrix
        try:
            inv_cov = np.linalg.inv(cov_matrix)
        except np.linalg.LinAlgError:
            # Use pseudo-inverse if matrix is singular
            inv_cov = np.linalg.pinv(cov_matrix)
            
        # Calculate Mahalanobis distances
        distances = []
        for control in control_pre_means:
            diff = pre_treatment - control
            distance = np.sqrt(diff.dot(inv_cov).dot(diff.T))[0, 0]
            distances.append(distance)
            
        # Convert to array
        distances = np.array(distances)
        
        # Get indices of the 5 closest matches
        n_matches = min(5, len(distances))
        match_indices = np.argsort(distances)[:n_matches]
        
        # Calculate matched control effect
        matched_pre_outcomes = control_pre_outcomes[match_indices]
        matched_post_outcomes = control_post_outcomes[match_indices]
        
        matched_effects = matched_post_outcomes - matched_pre_outcomes
        
        # Return average matched effect
        return np.mean(matched_effects)
    
    def synthetic_control_analysis(self,
                                 treatment_data: pd.DataFrame,
                                 control_pool: List[pd.DataFrame],
                                 control_names: List[str],
                                 treatment_date: datetime,
                                 outcome_variable: str,
                                 pre_period: int = 30,
                                 post_period: int = 30) -> Dict[str, Any]:
        """
        Perform synthetic control analysis.
        
        Args:
            treatment_data: DataFrame with treatment unit data
            control_pool: List of DataFrames with control unit data
            control_names: Names of control units
            treatment_date: Treatment date
            outcome_variable: Variable to measure treatment effect on
            pre_period: Days before treatment for pre-treatment period
            post_period: Days after treatment for post-treatment period
            
        Returns:
            dict: Synthetic control analysis results
        """
        if not STATSMODELS_AVAILABLE:
            logger.error("statsmodels required for synthetic control analysis")
            return {"error": "statsmodels not available"}
            
        # Check input validity
        if len(control_pool) != len(control_names):
            logger.error("control_pool and control_names must have same length")
            return {"error": "Mismatched control pool and names"}
            
        if len(control_pool) == 0:
            logger.error("No control units provided")
            return {"error": "No control units"}
            
        # Ensure all DataFrames have datetime indices
        if not isinstance(treatment_data.index, pd.DatetimeIndex):
            logger.error("treatment_data must have DatetimeIndex")
            return {"error": "Invalid treatment data format"}
            
        for control_df in control_pool:
            if not isinstance(control_df.index, pd.DatetimeIndex):
                logger.error("All control DataFrames must have DatetimeIndex")
                return {"error": "Invalid control data format"}
                
        # Find treatment date in data
        if treatment_date not in treatment_data.index:
            closest_date = treatment_data.index[treatment_data.index.get_indexer([treatment_date], method='nearest')[0]]
            logger.warning(f"Treatment date {treatment_date} not found, using closest date {closest_date}")
            treatment_date = closest_date
            
        # Get treatment index
        treatment_idx = treatment_data.index.get_loc(treatment_date)
        
        # Define pre and post periods
        pre_start = max(0, treatment_idx - pre_period)
        pre_end = treatment_idx
        post_start = treatment_idx + 1
        post_end = min(len(treatment_data), treatment_idx + post_period + 1)
        
        # Get data for periods
        pre_data = treatment_data.iloc[pre_start:pre_end]
        post_data = treatment_data.iloc[post_start:post_end]
        
        # Check if we have enough data
        if len(pre_data) < 10 or len(post_data) < 1:
            logger.error("Insufficient data for synthetic control analysis")
            return {"error": "Insufficient data"}
            
        # Prepare data for synthetic control
        # Extract outcome variable
        Y1 = pre_data[outcome_variable].values
        
        # Extract control outcomes
        Y0 = np.zeros((len(Y1), len(control_pool)))
        
        for i, control_df in enumerate(control_pool):
            # Find treatment date in control data
            if treatment_date not in control_df.index:
                # Find closest date
                closest_date = control_df.index[control_df.index.get_indexer([treatment_date], method='nearest')[0]]
                logger.warning(f"Treatment date {treatment_date} not found in control {control_names[i]}, "
                             f"using closest date {closest_date}")
                control_treatment_date = closest_date
            else:
                control_treatment_date = treatment_date
                
            # Get control index
            control_idx = control_df.index.get_loc(control_treatment_date)
            
            # Define control pre period
            control_pre_start = max(0, control_idx - pre_period)
            control_pre_end = control_idx
            
            # Get control pre data
            control_pre = control_df.iloc[control_pre_start:control_pre_end]
            
            # Check if we have enough data
            if len(control_pre) < len(Y1):
                # Pad with missing values
                padded = np.full(len(Y1), np.nan)
                padded[-len(control_pre):] = control_pre[outcome_variable].values
                Y0[:, i] = padded
            else:
                Y0[:, i] = control_pre[outcome_variable].values[-len(Y1):]
                
        # Handle missing values
        Y0_mask = ~np.isnan(Y0)
        
        # If any control has all missing values, remove it
        valid_controls = Y0_mask.sum(axis=0) > 0
        if np.sum(valid_controls) == 0:
            logger.error("No valid control units")
            return {"error": "No valid control units"}
            
        Y0 = Y0[:, valid_controls]
        valid_control_names = [control_names[i] for i, valid in enumerate(valid_controls) if valid]
        
        # Synthetic control weights estimation
        # This is a simplified implementation
        # In practice, you might want to use specialized libraries or more sophisticated methods
        
        # Solve for optimal weights (minimize squared prediction error)
        try:
            # Calculate cross-product matrices
            Z = Y0.T.dot(Y0)
            
            # Handle singularity
            if np.linalg.matrix_rank(Z) < Z.shape[0]:
                # Add small regularization
                Z = Z + np.eye(Z.shape[0]) * 1e-6
                
            # Calculate weights
            weights = np.linalg.solve(Z, Y0.T.dot(Y1))
            
            # Ensure weights are positive and sum to 1
            weights = np.maximum(weights, 0)
            weights = weights / np.sum(weights)
            
        except Exception as e:
            logger.error(f"Error estimating synthetic control weights: {e}")
            
            # Fallback to equal weights
            weights = np.ones(Y0.shape[1]) / Y0.shape[1]
            
        # Compute synthetic control
        pre_synthetic = Y0.dot(weights)
        
        # Calculate pre-treatment fit
        pre_rmse = np.sqrt(np.mean((Y1 - pre_synthetic) ** 2))
        pre_mae = np.mean(np.abs(Y1 - pre_synthetic))
        
        # Get post-treatment data for all units
        Y1_post = post_data[outcome_variable].values
        
        Y0_post = np.zeros((len(Y1_post), len(control_pool)))
        
        for i, control_df in enumerate(control_pool):
            if not valid_controls[i]:
                continue
                
            # Find treatment date in control data
            if treatment_date not in control_df.index:
                control_treatment_date = control_df.index[control_df.index.get_indexer([treatment_date], method='nearest')[0]]
            else:
                control_treatment_date = treatment_date
                
            # Get control index
            control_idx = control_df.index.get_loc(control_treatment_date)
            
            # Define control post period
            control_post_start = control_idx + 1
            control_post_end = min(len(control_df), control_idx + post_period + 1)
            
            # Get control post data
            control_post = control_df.iloc[control_post_start:control_post_end]
            
            # Check if we have enough data
            if len(control_post) < len(Y1_post):
                # Pad with missing values
                padded = np.full(len(Y1_post), np.nan)
                padded[:len(control_post)] = control_post[outcome_variable].values
                Y0_post[:, i] = padded
            else:
                Y0_post[:, i] = control_post[outcome_variable].values[:len(Y1_post)]
                
        # Filter to valid controls
        Y0_post = Y0_post[:, valid_controls]
        
        # Compute post-treatment synthetic control
        post_synthetic = Y0_post.dot(weights)
        
        # Calculate treatment effect
        treatment_effect = Y1_post - post_synthetic
        
        # Calculate aggregate metrics
        mean_effect = np.mean(treatment_effect)
        cumulative_effect = np.sum(treatment_effect)
        
        # Estimate placebo treatment effects for inference
        if len(valid_control_names) >= 5:
            placebo_effects = []
            
            # Use each control as a placebo treatment
            for i, control_name in enumerate(valid_control_names):
                # Create placebo control pool
                placebo_treatment = control_pool[control_names.index(control_name)]
                placebo_controls = [control_pool[control_names.index(name)] for name in control_names 
                                  if name != control_name]
                placebo_control_names = [name for name in control_names if name != control_name]
                
                # Run synthetic control for placebo
                placebo_result = self.synthetic_control_analysis(
                    placebo_treatment, placebo_controls, placebo_control_names,
                    treatment_date, outcome_variable, pre_period, post_period)
                
                # Check if valid result
                if 'error' not in placebo_result and 'mean_effect' in placebo_result:
                    placebo_effects.append(placebo_result['mean_effect'])
                    
            # Calculate p-value based on placebo distribution
            if placebo_effects:
                placebo_effects = np.array(placebo_effects)
                p_value = np.mean(np.abs(placebo_effects) >= np.abs(mean_effect))
                significant = p_value < 0.05
            else:
                p_value = None
                significant = None
        else:
            placebo_effects = []
            p_value = None
            significant = None
            
        # Prepare result
        result = {
            'method': 'synthetic_control',
            'pre_rmse': float(pre_rmse),
            'pre_mae': float(pre_mae),
            'weights': dict(zip(valid_control_names, weights.tolist())),
            'mean_effect': float(mean_effect),
            'cumulative_effect': float(cumulative_effect),
            'treatment_effect': treatment_effect.tolist(),
            'p_value': p_value,
            'significant': significant,
            'pre_data': {
                'treatment': Y1.tolist(),
                'synthetic': pre_synthetic.tolist()
            },
            'post_data': {
                'treatment': Y1_post.tolist(),
                'synthetic': post_synthetic.tolist()
            }
        }
        
        # Store analysis results
        analysis_id = f"synthetic_control_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.analysis_results[analysis_id] = result
        
        return result
    
    def plot_causal_impact(self, result: Dict[str, Any], output_file: Optional[str] = None) -> None:
        """
        Plot causal impact analysis results.
        
        Args:
            result: Causal impact analysis result
            output_file: Path to save the plot
        """
        if 'error' in result:
            logger.error(f"Cannot plot result with error: {result['error']}")
            return
            
        try:
            import matplotlib.pyplot as plt
            
            # Create figure with multiple panels
            fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
            
            # Determine data based on result type
            if result.get('method') == 'causalimpact':
                # CausalImpact result format
                if 'data' in result:
                    # Get original data
                    data = result['data']
                    dates = pd.date_range(start=data['dates'][0], periods=len(data['dates']))
                    
                    # Plot original and counterfactual
                    axes[0].plot(dates, data['original'], 'b-', label='Observed')
                    axes[0].plot(dates, data['predicted'], 'r--', label='Counterfactual')
                    axes[0].axvline(x=dates[data['pre_period'][1]], color='gray', linestyle='--')
                    axes[0].set_title('Original vs Counterfactual')
                    axes[0].legend()
                    
                    # Plot point effects
                    axes[1].plot(dates[data['pre_period'][1]+1:], data['point_effects'], 'g-')
                    axes[1].axhline(y=0, color='gray', linestyle='--')
                    axes[1].set_title('Point Effects')
                    
                    # Plot cumulative effects
                    axes[2].plot(dates[data['pre_period'][1]+1:], data['cumulative_effects'], 'g-')
                    axes[2].axhline(y=0, color='gray', linestyle='--')
                    axes[2].set_title('Cumulative Effect')
                else:
                    logger.error("CausalImpact result does not contain data")
                    return
                    
            elif result.get('method') == 'synthetic_control':
                # Synthetic control result format
                # Create date index (dummy dates if not available)
                pre_len = len(result['pre_data']['treatment'])
                post_len = len(result['post_data']['treatment'])
                
                dates = pd.date_range(start='2000-01-01', periods=pre_len + post_len)
                pre_dates = dates[:pre_len]
                post_dates = dates[pre_len:]
                
                # Plot original and synthetic control
                axes[0].plot(pre_dates, result['pre_data']['treatment'], 'b-', label='Treated Unit')
                axes[0].plot(pre_dates, result['pre_data']['synthetic'], 'r--', label='Synthetic Control')
                axes[0].plot(post_dates, result['post_data']['treatment'], 'b-')
                axes[0].plot(post_dates, result['post_data']['synthetic'], 'r--')
                axes[0].axvline(x=dates[pre_len-1], color='gray', linestyle='--')
                axes[0].set_title('Treated Unit vs Synthetic Control')
                axes[0].legend()
                
                # Plot point effects
                axes[1].plot(post_dates, result['treatment_effect'], 'g-')
                axes[1].axhline(y=0, color='gray', linestyle='--')
                axes[1].set_title('Treatment Effect')
                
                # Plot cumulative effect
                cumulative_effect = np.cumsum(result['treatment_effect'])
                axes[2].plot(post_dates, cumulative_effect, 'g-')
                axes[2].axhline(y=0, color='gray', linestyle='--')
                axes[2].set_title('Cumulative Effect')
                
            else:
                # DID or other method
                # We don't have detailed time series, so plot a simple bar chart
                fig, ax = plt.subplots(figsize=(8, 6))
                
                # Plot average treatment effect
                ax.bar(['Pre-Treatment', 'Post-Treatment', 'Counterfactual', 'Effect'], 
                      [result.get('pre_avg', 0), result.get('post_avg', 0),
                       result.get('pre_avg', 0) + result.get('matched_effect', 0),
                       result.get('avg_effect', 0)])
                
                ax.set_title('Treatment Effect Analysis')
                ax.grid(True, alpha=0.3)
                
                # Add significance marker if available
                if result.get('significant') is not None:
                    if result.get('significant'):
                        ax.text(3, result.get('avg_effect', 0) / 2, 
                              'Significant (p < 0.05)', ha='center')
                    else:
                        ax.text(3, result.get('avg_effect', 0) / 2, 
                              'Not Significant', ha='center')
            
            # Add summary text
            summary_text = (
                f"Method: {result.get('method', 'Unknown')}\n"
                f"Average Effect: {result.get('avg_effect', result.get('mean_effect', 0)):.4f}\n"
                f"p-value: {result.get('p_value', 'N/A')}\n"
                f"Significant: {result.get('significant', 'N/A')}"
            )
            
            fig.text(0.1, 0.01, summary_text, fontsize=12, 
                    bbox=dict(facecolor='white', alpha=0.8))
            
            # Adjust layout
            plt.tight_layout(rect=[0, 0.04, 1, 0.96])
            
            # Save or display
            if output_file:
                plt.savefig(output_file, dpi=300, bbox_inches='tight')
                logger.info(f"Plot saved to {output_file}")
            else:
                plt.show()
                
            plt.close()
            
        except ImportError:
            logger.warning("Matplotlib not available. Cannot generate plot.")
        except Exception as e:
            logger.error(f"Error plotting causal impact: {e}")
    
    def save_analysis_results(self, analysis_id: Optional[str] = None, 
                            filename: Optional[str] = None) -> str:
        """
        Save analysis results to file.
        
        Args:
            analysis_id: ID of analysis to save (if None, save all)
            filename: Output filename (if None, generate based on timestamp)
            
        Returns:
            str: Path to saved file
        """
        # Default filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if analysis_id:
                filename = os.path.join(self.output_dir, f"{analysis_id}_{timestamp}.json")
            else:
                filename = os.path.join(self.output_dir, f"causal_analysis_{timestamp}.json")
                
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Extract results to save
        if analysis_id:
            if analysis_id not in self.analysis_results:
                logger.error(f"Analysis ID {analysis_id} not found")
                return ""
                
            results_to_save = {analysis_id: self.analysis_results[analysis_id]}
        else:
            results_to_save = self.analysis_results
            
        # Convert numpy types and other non-serializable types
        def convert_for_json(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, pd.DataFrame):
                return obj.to_dict()
            elif isinstance(obj, pd.Series):
                return obj.to_dict()
            elif isinstance(obj, datetime):
                return obj.strftime('%Y-%m-%d %H:%M:%S')
            return obj
            
        # Save to file
        try:
            with open(filename, 'w') as f:
                json.dump(results_to_save, f, default=convert_for_json, indent=2)
                
            logger.info(f"Analysis results saved to {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error saving analysis results: {e}")
            return ""
        
    def load_analysis_results(self, filename: str) -> bool:
        """
        Load analysis results from file.
        
        Args:
            filename: Path to file
            
        Returns:
            bool: Success flag
        """
        if not os.path.exists(filename):
            logger.error(f"File not found: {filename}")
            return False
            
        try:
            with open(filename, 'r') as f:
                loaded_results = json.load(f)
                
            # Update analysis results
            self.analysis_results.update(loaded_results)
            
            logger.info(f"Loaded analysis results from {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading analysis results: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Create causal inference framework
    ci = CausalInferenceFramework()
    
    # Generate synthetic data for demonstration
    np.random.seed(42)
    
    # Generate dates
    dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
    
    # Create treatment data
    treatment_data = pd.DataFrame({
        'close': 100 + np.cumsum(np.random.normal(0.001, 0.01, 100)),
        'volume': np.random.lognormal(10, 1, 100),
        'volatility': np.random.uniform(0.01, 0.03, 100)
    }, index=dates)
    
    # Add intervention effect starting at day 50
    intervention_date = dates[50]
    treatment_data.loc[dates[50:], 'close'] += np.linspace(0, 2, 50)
    
    # Create control data (3 control units)
    control_pool = []
    control_names = []
    
    for i in range(3):
        control = pd.DataFrame({
            'close': 100 + np.cumsum(np.random.normal(0.001, 0.01, 100)),
            'volume': np.random.lognormal(10, 1, 100),
            'volatility': np.random.uniform(0.01, 0.03, 100)
        }, index=dates)
        
        control_pool.append(control)
        control_names.append(f"Control_{i+1}")
    
    # Perform causal validation
    causal_validation = ci.causal_strategy_validation(
        treatment_data, [intervention_date], ['buy'], 
        pre_period=20, post_period=20)
    
    print("Causal Strategy Validation Results:")
    print(f"Overall Average Treatment Effect: {causal_validation['overall']['avg_treatment_effect']:.4f}")
    print(f"Significant Signals: {causal_validation['overall']['significant_signals']}/{causal_validation['overall']['num_signals']}")
    
    # Plot the first signal result
    if causal_validation['signals']:
        ci.plot_causal_impact(causal_validation['signals'][0], 'causal_validation.png')
    
    # Perform synthetic control analysis
    synthetic_control = ci.synthetic_control_analysis(
        treatment_data, control_pool, control_names,
        intervention_date, 'close', pre_period=20, post_period=20)
    
    print("\nSynthetic Control Analysis Results:")
    print(f"Mean Effect: {synthetic_control['mean_effect']:.4f}")
    print(f"Cumulative Effect: {synthetic_control['cumulative_effect']:.4f}")
    print(f"p-value: {synthetic_control['p_value']}")
    print(f"Significant: {synthetic_control['significant']}")
    
    # Plot synthetic control result
    ci.plot_causal_impact(synthetic_control, 'synthetic_control.png')
    
    # Save analysis results
    results_file = ci.save_analysis_results(filename='causal_analysis_results.json')
    print(f"\nAnalysis results saved to {results_file}")