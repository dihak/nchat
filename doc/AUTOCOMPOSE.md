Auto-Compose
============
The nchat bundled default auto-compose utility `compose` uses external
services for chat completion, and generally requires an API key
(set in environment) to work. Environment variables to set:

    OpenAI: OPENAI_API_KEY
    Gemini: GEMINI_API_KEY


Basic Testing
-------------
An [example chat history file](/doc/example-history.txt) is provided for
testing chat completion standalone. Example:

    ./src/compose -c doc/example-history.txt


Testing Services / Models
-------------------------
The utility `compose` may be used with OpenAI-compatible services.

Example usage with default service (OpenAI) and default model (gpt-4o-mini):

    ./src/compose -c doc/example-history.txt

Example usage with OpenAI:

    ./src/compose -s openai -c doc/example-history.txt

Example usage with OpenAI and custom model and longer timeout of 60 secs:

    ./src/compose -s openai -m gpt-5-nano -T 60 -c doc/example-history.txt

Example usage with Google Gemini:

    ./src/compose -s gemini -c doc/example-history.txt

Example usage with Google Gemini and custom model:

    ./src/compose -s gemini -m gemini-2.5-flash -c doc/example-history.txt

Example usage with llama.cpp:

    ./src/compose -s "http://192.168.10.159:8080" -c doc/example-history.txt

Example starting llama.cpp server:

    llama-server --port 8080 -m ./models/llama-2-13b-chat.Q4_K_M.gguf


Configuring Custom Service / Model
----------------------------------
Edit `ui.conf` to match the desired compose path and usage.

The `compose` script is bundled inside the nchat executable and extracted to
a temporary location at runtime, so there is no installed copy to reference.
To use custom arguments, copy [compose](/src/compose) from the source tree
(or download it) to a location of your choice, e.g:

    cp src/compose ~/.local/bin/compose

Example usage with Google Gemini and custom model:

    auto_compose_command=python3 ~/.local/bin/compose -s gemini -m gemini-2.0-flash -c '%1'

Example usage with OpenAI and custom model and longer timeout of 60 secs:

    auto_compose_command=python3 ~/.local/bin/compose -s openai -m gpt-5-nano -T 60 -c '%1'

Example usage with custom prompt and max token limit of 100:

    auto_compose_command=python3 ~/.local/bin/compose -p "Suggest {your_name}'s next reply in a joking manner." -M 100 -c '%1'


Config-file compose (`utils/nchat-compose`)
------------------------------------------
`nchat-compose` does not hardcode an API host, model, or key. It reads a separate
key=value `compose.conf` (not `ui.conf`):

    base_url=https://api.example.com/v1
    api_backend=responses
    model=demo-model
    api_key_env=MY_API_KEY,FALLBACK_API_KEY
    timeout=60

Required keys:

- `base_url` — origin only, no path suffix (example: `https://api.example.com/v1`)
- `api_backend` — `responses` or `chat_completions`
- `model` — model id sent to the API
- `api_key_env` — comma-separated **names** of environment variables; the first
  non-empty value is used as the Bearer token (do not put the key in the file)

Optional: `timeout` seconds (default 60).

Backends:

- `responses` → `POST {base_url}/responses` with `{"model","input"}`
- `chat_completions` → `POST {base_url}/chat/completions` with `messages`

Config path: `-f PATH`, or env `NCHAT_COMPOSE_CONFIG`.

    auto_compose_command=python3 ~/.local/bin/nchat-compose -f /path/to/compose.conf -c '%1'

If the config or API key is missing, or the request fails, the script exits
non-zero with a message on stderr and prints nothing on stdout.

While the command runs, the status bar shows `composing...`. Press the
auto-compose key again, or the cancel key, to abort it. The draft is written
into the input box only after the command exits successfully.

The entry area has a second line, `ai:`. Down from the end of the message
moves the cursor there. Up moves it back. Enter sends only the message line.

Ctrl-x sends the ask line, the current draft, and the recent chat. An empty
ask line and an empty draft asks for the next reply. Any other ask text is
the instruction (translate, fix grammar, shorten, and so on). The ask line
is cleared when a result is applied.

