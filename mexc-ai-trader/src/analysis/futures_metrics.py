"""Deprecated futures module — re-exports spot metrics for compatibility."""

from src.analysis.spot_metrics import analyze_futures_metrics, analyze_spot_metrics

__all__ = ["analyze_spot_metrics", "analyze_futures_metrics"]
