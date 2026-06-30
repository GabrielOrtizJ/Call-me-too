import json
import pathlib
import re
import sys
import time
from typing import Any, List, Set, Optional

from llm_sdk import Small_LLM_Model
from . import get_definitions, get_tests, Config, ParserException
from enum import Enum, auto


class Stage(Enum):
    START = auto()                      # {

    OPEN_QUOTE_PROMPT_KEY = auto()      # "
    PROMPT_KEY = auto()                 # prompt
    CLOSE_QUOTE_PROMPT_KEY = auto()     # "
    COLON_PROMPT_KEY = auto()           # :
    OPEN_QUOTE_PROMPT_VALUE = auto()    # "
    PROMPT_VALUE = auto()               # prompt str
    CLOSE_QUOTE_PROMPT_VALUE = auto()   # "
    COMMA_AFTER_PROMPT = auto()         # ,

    OPEN_QUOTE_FN_KEY = auto()          # "
    FN_KEY = auto()                     # fn_name
    CLOSE_QUOTE_FN_KEY = auto()         # "
    COLON_FN_KEY = auto()               # :
    OPEN_QUOTE_FN_VALUE = auto()        # "
    FN_VALUE = auto()                   # function name
    CLOSE_QUOTE_FN_VALUE = auto()       # "
    COMMA_AFTER_FN = auto()             # ,

    OPEN_QUOTE_ARGS_KEY = auto()        # "
    ARGS_KEY = auto()                   # args
    CLOSE_QUOTE_ARGS_KEY = auto()       # "
    COLON_ARGS_KEY = auto()             # :
    OPEN_BRACE_ARGS_VALUE = auto()      # {

    OPEN_QUOTE_ARG_KEY = auto()         # "
    ARG_KEY = auto()                    # each argument name
    CLOSE_QUOTE_ARG_KEY = auto()        # "
    COLON_ARG = auto()                  # :
    ARG_VALUE = auto()                  # argument value
    END_ARG_QUOTE = auto()
    COMMA_ARG = auto()                  # , between arguments

    CLOSE_BRACE_ARGS_VALUE = auto()     # }
    CLOSE_BRACE_JSON = auto()           # }
    END = auto()                        # finished


def load_functions_context(config: Config,
                           definitions: list[dict[str, Any]]) -> None:
    # fetch function names and args
    config.functions_format = {}
    config.function_name_encodings = {}
    prompt_context = "Available functions:"
    for definition in definitions:
        fn_name = str(definition.get("fn_name"))
        config.functions_format[fn_name] = []
        config.function_name_encodings[fn_name] = \
            config.model.encode(fn_name)[0].tolist()
        prompt_context += f"{fn_name}, "

        args_names = definition.get("args_names", [])
        if isinstance(args_names, list):
            for arg in args_names:
                arg = str(arg)
                arg_name: List[int] = config.model.encode(arg)[0].tolist()
                args_types = definition.get("args_types", {})
                if isinstance(args_types, dict):
                    arg_type = args_types.get(arg, None)
                    config.functions_format[fn_name].append({
                        'type': str(arg_type) if arg_type else "str",
                        'name': arg_name
                    })

    # set prompt logits
    prompt_context = prompt_context[:-2] + ". JSON result: "
    config.context_ids = config.model.encode(prompt_context)[0].tolist()

    # load vocab
    vocab_path = config.model.get_path_to_vocabulary_json()
    try:
        with open(vocab_path, "r") as f:
            config.token_to_id = json.load(f)
            config.id_to_token = {id: token
                                  for (token, id)
                                  in config.token_to_id.items()}
        config.numbers_vocab = [config.token_to_id[str(v)]
                                for v in range(10)] +\
                               [config.token_to_id["-"]]
    except (FileNotFoundError, PermissionError, OSError):
        raise ParserException(f"Could not fetch vocab at '{vocab_path}'")


def fix_odd_single_quotes(match: re.Match[str]) -> str:
    s = match.group(1)
    if s.count("'") % 2 == 1:
        s = s.rstrip("'")
    return f'"{s}"'


def calculate_logits(config: Config, current_ids: list[int]) -> list[float]:
    logits: list[float] = config.model.get_logits_from_input_ids(current_ids)
    return logits


def compute_output(config: Config, prompt: str) -> Optional[dict[str, Any]]:
    # load list of chars
    assert config.token_to_id
    assert config.id_to_token
    assert config.context_ids
    assert config.functions_format
    assert config.function_name_encodings
    assert config.numbers_vocab

    QUOTES_LIST: Set[Stage] = {
        Stage.OPEN_QUOTE_PROMPT_KEY,
        Stage.CLOSE_QUOTE_PROMPT_KEY,
        Stage.OPEN_QUOTE_PROMPT_VALUE,
        Stage.CLOSE_QUOTE_PROMPT_VALUE,
        Stage.OPEN_QUOTE_FN_KEY,
        Stage.CLOSE_QUOTE_FN_KEY,
        Stage.OPEN_QUOTE_FN_VALUE,
        Stage.OPEN_QUOTE_ARGS_KEY,
        Stage.CLOSE_QUOTE_FN_VALUE,
        Stage.CLOSE_QUOTE_ARGS_KEY,
        Stage.OPEN_QUOTE_ARG_KEY,
        Stage.CLOSE_QUOTE_ARG_KEY,
        Stage.END_ARG_QUOTE
    }

    COLON_LIST: Set[Stage] = {
        Stage.COLON_ARG,
        Stage.COLON_ARGS_KEY,
        Stage.COLON_FN_KEY,
        Stage.COLON_PROMPT_KEY,
    }

    COMMA_LIST: Set[Stage] = {
        Stage.COMMA_AFTER_PROMPT,
        Stage.COMMA_AFTER_FN,
        Stage.COMMA_ARG,
    }

    # load prompt
    prompt_ids_raw: List[int] = config.model.encode(prompt)[0].tolist()
    prompt_ids: List[int] = []

    # handle characters
    for idx in prompt_ids_raw:
        token = config.id_to_token[idx]
        if (
            len(token) > 2
            and (token.startswith("'") or token.startswith("Ġ'"))
            and token.endswith("'")
        ):
            parts = token.split("'")
            prompt_ids.append(config.token_to_id[parts[0] + "'"])
            prompt_ids.append(config.token_to_id[parts[1]])
            prompt_ids.append(config.token_to_id["'"])
        else:
            prompt_ids.append(idx)

    current_ids = list[int](config.context_ids + prompt_ids)
    prompt_ids_l = len(prompt_ids)

    # FSM
    state = Stage.START
    progress: str = ""
    progress_i = 0
    progress_j = 0
    selected_function: str = ""

    if prompt.strip() == "":
        fn = next(iter(config.functions_format), None)
        if fn is None:
            raise ParserException("No available functions")

        return {
            "prompt": "",
            "fn_name": fn,
            "args": {
                config.model.decode(dic["name"]): (
                    "" if dic["type"] == "str"
                    else 0 if dic["type"] == "int"
                    else 0.0 if dic["type"] == "float"
                    else None
                )
                for dic in config.functions_format[fn]
            }
        }

    while state != Stage.END:
        allowed = set()
        logits: List[float] = []

        match (state):
            case Stage.START | Stage.OPEN_BRACE_ARGS_VALUE:
                allowed = {config.token_to_id["{"]}
            case _ if state in QUOTES_LIST:
                allowed = {config.token_to_id['"']}
            case Stage.PROMPT_KEY:
                allowed = {config.token_to_id["prompt"]}
            case _ if state in COLON_LIST:
                allowed = {config.token_to_id[":"]}
            case Stage.PROMPT_VALUE:
                if progress_i < prompt_ids_l:
                    allowed = {prompt_ids[progress_i]}
            case _ if state in COMMA_LIST:
                allowed = {config.token_to_id[","]}
            case _ if state in [Stage.CLOSE_BRACE_ARGS_VALUE,
                                Stage.CLOSE_BRACE_JSON]:
                allowed = {config.token_to_id["}"]}
            case Stage.FN_KEY:
                current_ids.append(config.token_to_id['fn'])
                allowed = {config.token_to_id["_name"]}
            case Stage.FN_VALUE:
                current_text = progress
                # calculate logits again
                logits = calculate_logits(config, current_ids)
                for name in config.functions_format.keys():
                    enc: List[int] = config.function_name_encodings[name]
                    l_enc = len(enc)
                    if name.startswith(current_text) and progress_i < l_enc:
                        allowed |= {enc[progress_i]}
                        logits[enc[progress_i]] = sum([
                            logits[x] for x in enc
                            ]) / l_enc
            case Stage.ARGS_KEY:
                allowed = {config.token_to_id["args"]}
            case Stage.ARG_KEY:
                if len(selected_function) > 0:
                    arg_def = config.functions_format[
                        selected_function][progress_i]
                    allowed = {
                        int(arg_def.get('name', "")[progress_j])
                    }
            case Stage.ARG_VALUE:
                s: str = selected_function
                arg: dict[str, Any] = config.functions_format[s][progress_i]
                arg_type: str = arg.get("type", "")

                if arg_type == "str" and prompt_ids_l == 0:
                    allowed = {config.token_to_id['"']}
                elif len(progress) == 0 and arg_type == "str":
                    allowed = {config.token_to_id['"']}
                else:
                    allowed = set(prompt_ids)
                    for pid in prompt_ids:
                        token = config.id_to_token[pid]
                        if token.startswith("Ġ"):
                            stripped = token[1:]
                            if stripped in config.token_to_id:
                                allowed.add(config.token_to_id[stripped])

                    if arg_type == "int":
                        allowed &= set(config.numbers_vocab)
                    elif arg_type == "float":
                        allowed &= set(config.numbers_vocab +
                                       [config.token_to_id["."]])
                    elif arg_type == "str":
                        allowed -= {config.token_to_id["'"]}
            case Stage.END:
                break

        if len(allowed) > 0:  # apply mask
            if len(allowed) == 1:  # avoid recalculation
                next_token = next(iter(allowed))
                current_ids.append(next_token)
            else:
                if len(logits) == 0:
                    logits = calculate_logits(config, current_ids)
                next_token = max(allowed, key=lambda x: logits[x])
                current_ids.append(next_token)

        # go the next stage
        if state == Stage.PROMPT_VALUE:
            progress_i += 1
            if progress_i >= prompt_ids_l:
                progress_i = 0
                state = Stage(state.value + 1)
        elif state == Stage.FN_VALUE:
            new_token_str = config.model.decode(next_token)
            progress += new_token_str
            progress_i += 1
            if not allowed:
                # remove last repeating occurrence
                selected_function = progress.removesuffix(new_token_str)
                progress_i = 0
                progress = ""
                state = Stage(state.value + 1)
        elif state == Stage.ARG_KEY:
            progress_j += 1
            if progress_j >= len(config.functions_format[selected_function]
                                 [progress_i]['name']):
                progress_j = 0
                state = Stage(state.value + 1)
        elif state == Stage.ARG_VALUE:
            progress += config.model.decode(next_token)

            progress_j += 1
            arg_def = config.functions_format[selected_function][progress_i]
            arg_type = str(arg_def.get("type", ""))
            current_text = progress.strip()

            should_end = (
                prompt_ids_l == 0
                or next_token == -1
                or current_text.strip('"') not in prompt
            )

            if should_end:
                progress = ""
                progress_j = 0
                if next_token != -1:
                    current_ids.pop()

                if arg_type == "str":
                    state = Stage.END_ARG_QUOTE
                else:
                    if progress_i < len(
                            config.functions_format[selected_function]) - 1:
                        progress_i += 1
                        state = Stage.COMMA_ARG
                    else:
                        state = Stage.CLOSE_BRACE_ARGS_VALUE
        elif state == Stage.END_ARG_QUOTE:
            if progress_i < len(
                    config.functions_format[selected_function]) - 1:
                progress_i += 1
                state = Stage.COMMA_ARG
            else:
                state = Stage.CLOSE_BRACE_ARGS_VALUE

        elif state == Stage.COMMA_ARG:
            state = Stage.OPEN_QUOTE_ARG_KEY
        else:
            # for all other stages, just increment to the next stage
            state = Stage(state.value + 1)

    generated_ids = current_ids[len(config.context_ids + prompt_ids):]
    result = config.model.decode(generated_ids)

    # extract prompt safely
    m = re.search(r'"prompt"\s*:\s*".*?"(?=,)', result)
    prompt_part = m.group(0) if m else None

    # remove prompt from string
    if prompt_part:
        result_wo_prompt = result.replace(prompt_part, '__PROMPT__')
    else:
        result_wo_prompt = result

    # remove spaces after quotes
    result_wo_prompt = re.sub(r'(".*?"\s*:\s*")\s+', r'\1', result_wo_prompt)
    # fix 00..0 => 0 (only ints)
    result_wo_prompt = re.sub(r'\b0{2,}\b', '0', result_wo_prompt)
    # replace all double quotes by a single
    result_wo_prompt = re.sub(r"'+", "'", result_wo_prompt)
    # fix if no ending quote
    result_wo_prompt = re.sub(
        r'(".*?")\s*:\s*"([^"]*?)(?=[,}])',
        lambda m: f'{m.group(1)}:"{m.group(2)}"',
        result_wo_prompt
    )

    # restore prompt
    if prompt_part:
        result = result_wo_prompt.replace('__PROMPT__', prompt_part)
    else:
        result = result_wo_prompt

    print("Prompt:", prompt)
    print("Result:", result)
    try:
        data: dict[str, Any] = json.loads(result)
        print()
        print("\033[33m======= [TESTING] =======\033[0m")
        print("\033[35mprompt: \033[0m", data["prompt"])
        print("\033[35mfn_name:\033[0m", data["fn_name"])
        for (name, value) in data["args"].items():
            print(f"\033[35margs:    \033[0m'{name}' = '{value}'")
        print("\033[32mSUCCESS\033[0m: Valid json format")
        return data
    except Exception:
        print("\033[31mERROR\033[0m: Invalid json format")
    print("==============================")
    return None


def main() -> None:
    input_file = "./data/input/function_calling_tests.json"
    output_file = "data/output/function_calling_results.json"
    definitions = "./data/input/functions_definition.json"
    argv = sys.argv[1:]
    argc = len(argv)
    i = 0
    while i < argc:
        arg = argv[i]
        if arg == "--input" and i + 1 < argc:
            input_file = argv[i + 1]
            i += 1
        elif arg == "--output" and i + 1 < argc:
            output_file = argv[i + 1]
            i += 1
        else:
            raise ParserException(f"Invalid input:\n\t'{arg}'")
        i += 1
    print("input:", input_file)
    print("output:", output_file)
    print("\n\n")
    model = Small_LLM_Model()
    config = Config(
        model=model,
        output_file=output_file,
        context_ids=[],
        functions_format={},
        numbers_vocab=[],
        token_to_id={},
        id_to_token={},
        function_name_encodings={},
        first_token_map=[]
    )
    load_functions_context(config, list(get_definitions(definitions)))
    prompts = [test.get("prompt") for test in get_tests(input_file)]
    output = []
    for prompt in prompts:
        if prompt is None:
            raise ParserException("Invalid prompt")
        start = time.time()
        # avoid json escaping
        prompt = prompt.replace('\\', '\\\\').replace('"', '\\"')
        result = compute_output(config, prompt)
        if result:
            output.append(result)
        else:
            exit(1)
        print(f"Finished prompt in {time.time() - start}s")
    # write output
    try:
        pathlib.Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Json saved as '{output_file}'")
    except Exception:
        raise ParserException(f"Could not save output to '{output_file}'")


if __name__ == "__main__":
    main()
