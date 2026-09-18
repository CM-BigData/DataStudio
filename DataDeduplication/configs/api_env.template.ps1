# Copy the commands you need into the current PowerShell session.
# Do not commit or paste real API keys into source files.

$env:TEXT_RERANK_API_BASE = "https://coding.dashscope.aliyuncs.com/v1"
$env:TEXT_RERANK_MODEL = "qwen3.6-plus"
$env:TEXT_RERANK_API_KEY = "<put-your-api-key-in-current-shell-only>"

# Optional. Use these only if separate embedding / vision / audio / ASR services are available.
$env:TEXT_EMBEDDING_API_BASE = ""
$env:TEXT_EMBEDDING_MODEL = ""
$env:TEXT_EMBEDDING_API_KEY = ""

# IMAGE/AUDIO/ASR endpoints can be custom JSON services. Workflow params define endpoint_path and input_field.
$env:IMAGE_EMBEDDING_API_BASE = ""
$env:IMAGE_EMBEDDING_MODEL = ""
$env:IMAGE_EMBEDDING_API_KEY = ""

$env:AUDIO_EMBEDDING_API_BASE = ""
$env:AUDIO_EMBEDDING_MODEL = ""
$env:AUDIO_EMBEDDING_API_KEY = ""

$env:ASR_API_BASE = ""
$env:ASR_MODEL = ""
$env:ASR_API_KEY = ""
