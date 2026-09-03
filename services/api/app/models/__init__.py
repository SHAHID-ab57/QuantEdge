"""ORM models package.

Importing this package registers every model on ``Base.metadata``; Alembic's
``env.py`` imports it to auto-discover tables for autogenerate.
"""

from app.models.backtest_run import BacktestRun
from app.models.base import BaseModel, TimestampMixin
from app.models.candle import Candle
from app.models.evaluation_benchmark_run import EvaluationBenchmarkRun
from app.models.exchange import Exchange
from app.models.experiment import (
    Experiment,
    ExperimentArtifact,
    ExperimentMetric,
    ExperimentTag,
)
from app.models.market import Market
from app.models.ml_dataset_build import MLDatasetBuild
from app.models.prediction import Prediction
from app.models.training import TrainingJob, TrainingJobLog

__all__ = [
    "BaseModel",
    "TimestampMixin",
    "BacktestRun",
    "Candle",
    "EvaluationBenchmarkRun",
    "Exchange",
    "Experiment",
    "ExperimentArtifact",
    "ExperimentMetric",
    "ExperimentTag",
    "Market",
    "MLDatasetBuild",
    "Prediction",
    "TrainingJob",
    "TrainingJobLog",
]
