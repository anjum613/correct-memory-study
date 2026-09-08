from __future__ import annotations

ALPHABET = frozenset(range(32, 127))
RESERVED = frozenset(b'.[]()|*+?\\^${}')
CLASS_RESERVED = frozenset(b'[]\\-^')

class InvalidInput(ValueError):
    pass

def parse(pattern, flags='NONE'):
    if type(pattern) is not bytes or len(pattern) > 64 or any((c not in ALPHABET for c in pattern)):
        raise InvalidInput('pattern bounds')
    if type(flags) is not str or flags not in {'NONE', 'ASCII_IGNORE_CASE'}:
        raise InvalidInput('flags')
    position = 0

    def case_set(members):
        result = set(members)
        if flags == 'ASCII_IGNORE_CASE':
            result.update((c + 32 for c in members if 65 <= c <= 90))
            result.update((c - 32 for c in members if 97 <= c <= 122))
        return frozenset(result)

    def character(in_class=False):
        nonlocal position
        reserved = CLASS_RESERVED if in_class else RESERVED
        if position >= len(pattern):
            raise InvalidInput('missing character')
        value = pattern[position]
        position += 1
        if value == 92:
            if position >= len(pattern) or pattern[position] not in reserved:
                raise InvalidInput('unsupported escape')
            value = pattern[position]
            position += 1
        elif value in reserved:
            raise InvalidInput('reserved character')
        return value

    def atom():
        nonlocal position
        if position == len(pattern):
            raise InvalidInput('missing atom')
        c = pattern[position]
        if c == 40:
            position += 1
            result = expression()
            if position >= len(pattern) or pattern[position] != 41:
                raise InvalidInput('unclosed group')
            position += 1
            return result
        if c == 46:
            position += 1
            return ('char', ALPHABET)
        if c == 91:
            position += 1
            complement = position < len(pattern) and pattern[position] == 94
            if complement:
                position += 1
            members = set()
            while position < len(pattern) and pattern[position] != 93:
                first = character(True)
                if position < len(pattern) and pattern[position] == 45:
                    position += 1
                    last = character(True)
                    if last < first:
                        raise InvalidInput('descending range')
                    members.update(range(first, last + 1))
                else:
                    members.add(first)
            if not members or position >= len(pattern):
                raise InvalidInput('empty/unclosed class')
            position += 1
            accepted = case_set(members)
            return ('char', ALPHABET - accepted if complement else accepted)
        return ('char', case_set({character()}))

    def sequence():
        nonlocal position
        children = []
        while position < len(pattern) and pattern[position] not in (41, 124):
            child = atom()
            if position < len(pattern) and pattern[position] in (42, 43, 63):
                operator = pattern[position]
                position += 1
                child = ({42: 'star', 43: 'plus', 63: 'optional'}[operator], child)
            children.append(child)
        return ('cat', tuple(children))

    def expression():
        nonlocal position
        alternatives = [sequence()]
        while position < len(pattern) and pattern[position] == 124:
            position += 1
            alternatives.append(sequence())
        return ('union', tuple(alternatives))
    result = expression()
    if position != len(pattern):
        raise InvalidInput('unexpected closing group')
    return result

def validate_request(pattern, records, flags='NONE'):
    if type(records) not in (list, tuple) or len(records) > 8 or any((type(record) is not bytes or len(record) > 64 or any((c not in ALPHABET for c in record)) for record in records)):
        raise InvalidInput('record bounds')
    return parse(pattern, flags)

def cells(pattern, records, flags):
    result = [int(flags == 'ASCII_IGNORE_CASE'), len(pattern), *pattern, len(records)]
    for record in records:
        result.extend((len(record), *record))
    return tuple(result)
