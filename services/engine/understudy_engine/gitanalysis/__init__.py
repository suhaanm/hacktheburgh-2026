"""Git analysis (GIT-1, PLG-2 git adapter, PRV-4): commit habits of a learner against reference experts.

Off by default (``UNDERSTUDY_X_GIT`` or ``UNDERSTUDY_X``); nothing here is imported by the P0 path. Import paths:

    from understudy_engine.gitanalysis.synth import RepoSpec, make_repo, make_cohort, load_truth    # synthetic repos with truth
    from understudy_engine.gitanalysis.source import GitSource                                       # the source plugin
    from understudy_engine.gitanalysis.service import habits                                         # the GET /git/habits payload
    from understudy_engine.gitanalysis.evaluate import evaluate_git                                  # the evaluation section

Pipeline: ``source`` (read-only ``git log``) -> ``digest`` (the local-model track's digests: enums only) -> ``records`` (numbers
and enums) -> ``features`` / ``compare`` (habits, bootstrap intervals, placebo) -> ``suggest`` (a fixed catalogue; wording only
through the privacy spine). ``cogseq`` maps commit sessions to programmer cogs for the genome alignment.
"""
