"""Run the existing fleet probes against the EXL3 candidate with explicit budgets."""
import argparse
import json
import math
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fleet-scripts', required=True)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--model', default='DeepSeek-v4.1-Flash-EXL3')
    parser.add_argument('--context', type=int)
    args = parser.parse_args()
    sys.path.insert(0, args.fleet_scripts)
    import brain_probe as probe

    def emit(check, ok, **detail):
        print(json.dumps({'check': check, 'ok': ok, **detail}), flush=True)
        if not ok:
            raise RuntimeError(f'{check} failed')

    def request(prompt, **kwargs):
        return probe.chat(args.base, args.model,
                          [{'role': 'user', 'content': prompt}], 1800,
                          chat_template_kwargs={'enable_thinking': False}, **kwargs)

    with urllib.request.urlopen(args.base + '/v1/models', timeout=30) as response:
        models = json.load(response)['data']
    match = next((m for m in models if m['id'] == args.model), None)
    emit('identity', bool(match) and match.get('max_model_len') == 600000, model=match)

    body, seconds = request('What is 17*19? Reply with the integer only.',
                            max_tokens=32, logprobs=True, top_logprobs=1)
    choice = body['choices'][0]
    content = (choice['message'].get('content') or '').strip()
    logprobs = (choice.get('logprobs') or {}).get('content') or []
    finite = bool(logprobs) and all(math.isfinite(t['logprob']) for t in logprobs)
    emit('arithmetic_and_logits', content == '323' and finite,
         content=content, seconds=seconds, usage=body.get('usage'))

    body, seconds = request('Read src/main.py using the read_file tool.',
                            tools=probe.TOOLS, tool_choice='auto', max_tokens=256)
    calls = body['choices'][0]['message'].get('tool_calls') or []
    good = False
    if calls:
        fn = calls[0]['function']
        good = fn['name'] == 'read_file' and json.loads(fn['arguments']).get('path') == 'src/main.py'
    emit('tool_call', good, calls=calls, seconds=seconds)

    messages = [
        {'role': 'user', 'content': 'Read src/main.py using the read_file tool.'},
        {'role': 'assistant', 'content': None, 'tool_calls': calls},
        {'role': 'tool', 'tool_call_id': calls[0]['id'],
         'content': 'The file contains exactly: DEPLOY_MARKER=V41_READY'},
        {'role': 'user', 'content': 'Reply with the value of DEPLOY_MARKER only.'},
    ]
    body, seconds = probe.chat(
        args.base, args.model, messages, 1800, tools=probe.TOOLS,
        chat_template_kwargs={'enable_thinking': False}, max_tokens=128)
    content = (body['choices'][0]['message'].get('content') or '').strip()
    emit('tool_result_roundtrip', content == 'V41_READY', content=content, seconds=seconds)

    body, seconds = request('Copy this Korean text exactly, without explanation: 안녕하세요 세계',
                            max_tokens=64)
    content = (body['choices'][0]['message'].get('content') or '').strip()
    emit('korean_copy', content == '안녕하세요 세계', content=content, seconds=seconds)

    if args.context:
        hay, counted, target = probe.fit_haystack_to_window(
            args.base, args.model, args.context, 'QX-4417-ZD', 1800)
        body, seconds = probe.chat(
            args.base, args.model, probe.context_messages(hay), 1800,
            chat_template_kwargs={'enable_thinking': False}, max_tokens=256)
        text = body['choices'][0]['message'].get('content') or ''
        actual = body.get('usage', {}).get('prompt_tokens', counted)
        dead, reason = probe.looks_degenerate(text)
        emit('context', actual is not None and actual >= target * .98
             and not dead and 'QX-4417-ZD' in text,
             requested_window=args.context, prompt_tokens=actual,
             content=text, seconds=seconds, degenerate=reason)

    payload = {'model': args.model, 'messages': [{'role': 'user',
               'content': 'Reply with exactly the word ready.'}],
               'temperature': 0, 'max_tokens': 32, 'stream': True,
               'chat_template_kwargs': {'enable_thinking': False}}
    req = urllib.request.Request(args.base + '/v1/chat/completions',
          data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    fragments, done = [], False
    with urllib.request.urlopen(req, timeout=120) as response:
        for line in response:
            if not line.startswith(b'data: '):
                continue
            raw = line[6:].strip()
            if raw == b'[DONE]':
                done = True
                break
            event = json.loads(raw)
            for choice in event.get('choices', []):
                fragments.append(choice.get('delta', {}).get('content') or '')
    text = ''.join(fragments).strip()
    emit('post_request_streaming', done and text.lower().rstrip('.') == 'ready', content=text)


if __name__ == '__main__':
    main()
