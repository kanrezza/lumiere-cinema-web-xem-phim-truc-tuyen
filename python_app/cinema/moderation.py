"""Vietnamese keyword rules for comment triage. A match requires human review."""

import re
import unicodedata
from functools import cache


REGIONAL_TARGETS = ('miền bắc', 'miền trung', 'miền nam', 'dân bắc', 'dân trung', 'dân nam', 'bắc kỳ', 'trung kỳ', 'nam kỳ')
PUBLIC_TARGETS = ('việt nam', 'đất nước', 'quốc gia', 'đảng', 'chính phủ', 'nhà nước', 'tổ quốc')
DIRECT_ABUSE = ('đồ ngu', 'cút đi', 'đi chết đi', 'mày ngu', 'thằng ngu', 'con ngu', 'óc chó', 'súc vật', 'tao sẽ giết mày', 'kill yourself', 'you are an idiot')
CONTEXT_ABUSE = ('ngu', 'rác rưởi', 'chó chết', 'súc vật', 'cặn bã', 'cút', 'khốn nạn', 'óc chó')
PROFANITY = ('địt mẹ', 'đụ má', 'đéo mẹ', 'địt con mẹ', 'mẹ kiếp', 'vãi lồn', 'cái lồn', 'fuck you', 'motherfucker')
EXACT_VIETNAMESE_PROFANITY = ('địt', 'đéo', 'lồn', 'cặc', 'đụ', 'đmm', 'đcm', 'dmm', 'dcm')
SENSITIVE = ('bán clip sex', 'xin clip sex', 'gửi ảnh khỏa thân', 'link 18+', 'mua bán dâm', 'tung ảnh nóng')
REGIONAL_SLURS = ('bắc kỳ chó', 'nam kỳ chó', 'trung kỳ chó', 'bắc kỳ cầy', 'parky chó')
PUBLIC_SLURS = ('đảng chó', 'địt mẹ việt nam', 'địt mẹ đảng', 'đụ má việt nam')


def normalize(text, fold=False):
    text = unicodedata.normalize('NFKC', text).casefold()
    text = ''.join(char for char in text if unicodedata.category(char) != 'Cf')
    if fold:
        text = ''.join(char for char in unicodedata.normalize('NFD', text) if unicodedata.category(char) != 'Mn')
        text = text.replace('đ', 'd')
    return re.findall(r'[^\W_]+', text)


@cache
def rule_words(phrase, accept_unaccented):
    exact = normalize(phrase)
    folded = normalize(phrase, True) if accept_unaccented else exact
    return tuple(zip(exact, folded))


def phrase_positions(words, phrase, *, accept_unaccented=True):
    tokens = rule_words(phrase, accept_unaccented)
    length = len(tokens)
    return [(start, start + length) for start in range(len(words) - length + 1)
            if words[start] in tokens[0] and all(words[start + offset] in token for offset, token in enumerate(tokens[1:], 1))]


def matching_phrases(words, rules, *, accept_unaccented=True):
    return [phrase for phrase in rules if phrase_positions(words, phrase, accept_unaccented=accept_unaccented)]


def contextual_matches(clauses, targets):
    matches = []
    for clause in clauses:
        abuse_positions = {phrase: positions for phrase in CONTEXT_ABUSE + PROFANITY
                           if (positions := phrase_positions(clause, phrase))}
        if not abuse_positions:
            continue
        for target in targets:
            target_positions = phrase_positions(clause, target)
            for abuse, positions in abuse_positions.items():
                nearby = any(0 <= start - abuse_end <= 4 or 0 <= abuse_start - end <= 4
                             for start, end in target_positions for abuse_start, abuse_end in positions)
                if nearby:
                    match = f'{target} · {abuse}'
                    if match not in matches:
                        matches.append(match)
    return matches


def classify_comment_v1(content):
    """Keep these rules stable for the existing-comment data migration."""
    clauses = [normalize(part) for part in re.split(r'[.!?;…\n]+', content)]
    words = normalize(content)
    reasons = {
        'regional': list(dict.fromkeys(matching_phrases(words, REGIONAL_SLURS) + contextual_matches(clauses, REGIONAL_TARGETS))),
        'country_party': list(dict.fromkeys(matching_phrases(words, PUBLIC_SLURS) + contextual_matches(clauses, PUBLIC_TARGETS))),
        'harassment': matching_phrases(words, DIRECT_ABUSE),
        'sensitive': matching_phrases(words, SENSITIVE),
        'profanity': matching_phrases(words, PROFANITY) + matching_phrases(words, EXACT_VIETNAMESE_PROFANITY, accept_unaccented=False),
    }
    return {reason: phrases for reason, phrases in reasons.items() if phrases}
