import re

from django import template


register = template.Library()


@register.filter(name="non_whitespace_length")
def non_whitespace_length(value):
    """문자열에서 공백(띄어쓰기·줄바꿈·탭)을 제외한 글자 수를 반환합니다."""
    if value is None:
        return 0
    return len(re.sub(r"\s+", "", str(value)))
