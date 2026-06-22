# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

# Dollar threshold for auto-approval. Under this amount is instantly approved.
THRESHOLD = float(os.environ.get("EXPENSE_THRESHOLD", 100.0))

# Model name for the risk review judgment.
MODEL_NAME = os.environ.get("EXPENSE_MODEL", "gemini-3.1-flash-lite")
