from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from itertools import combinations
from typing import Any

from dedup_workflow_engine.utilities.vector import (
    call_openai_chat,
    call_json_api_endpoint,
    config_enabled,
    cosine_similarity,
    hashing_vector,
    missing_env_names,
    pairwise_topk,
)
from dedup_workflow_engine.operators.base import BaseOperator
