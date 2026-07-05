# -*- coding: utf-8 -*-
"""Views for basic writing activities (transcription and typing)"""

from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required


@login_required
@teacher_required
def transcription_view(request):
    """Redirect to unified_create with preset WRITING category and '필사(받아쓰기)' sub menu."""
    return redirect('/activities/create/?category=WRITING&sub=필사(받아쓰기)')


@login_required
@teacher_required
def typing_view(request):
    """Redirect to unified_create with preset WRITING category and '한글 타자 연습' sub menu."""
    return redirect('/activities/create/?category=WRITING&sub=한글 타자 연습')
