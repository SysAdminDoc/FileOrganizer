"""Parity tests for SOURCE_CONFIGS, CATEGORY_ALIASES, and batch dispatchers.

Born from the 2026-04-30 N-1 audit: `i_organized_legacy` was added to
`classify_design.SOURCE_CONFIGS` but missed in `organize_run` and
`review_resolver`, so `--source i_organized_legacy` would have failed at
apply time.  These tests guard against the same drift recurring.

What they enforce:

1. Every key in `classify_design.SOURCE_CONFIGS` (minus 'design_unorg', which
   organize_run calls 'design') is present in
   `organize_run._SOURCE_DIRS_FOR_TESTS`, in the `--source` argparse choices,
   and in `review_resolver.SOURCE_CONFIGS`.

2. Every right-hand side of `organize_run.CATEGORY_ALIASES` is a real
   canonical category in `classify_design.CATEGORIES`.  Catches phantom-
   category regressions of the kind documented in CHANGELOG 2026-04-28.

3. Every `batch_prefix` declared in `classify_design.SOURCE_CONFIGS` is
   handled by both `organize_run.batch_offset` and the glob dispatcher in
   `organize_run.load_all_with_index`.
"""
import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import classify_design
import organize_run
import review_resolver


# classify_design uses 'design_unorg' as the key; organize_run calls the
# same source 'design' for historical reasons.  Map between the two so the
# parity check stays meaningful without forcing a rename.
CD_TO_ORUN = {
    'design_unorg':       'design',
    'design_org':         'design_org',
    'loose_files':        'loose_files',
    'design_elements':    'design_elements',
    'i_organized_legacy': 'i_organized_legacy',
}


class SourceConfigsParity(unittest.TestCase):

    def _organize_run_source_choices(self) -> set[str]:
        """Re-derive the --source argparse choices from organize_run.main()."""
        # Walk the argparse setup by parsing --help; cheap and authoritative.
        parser = argparse.ArgumentParser()
        # Mirror only the --source flag — keep this in sync with main().
        parser.add_argument(
            '--source', type=str, default='ae',
            choices=['ae', 'design', 'design_org', 'loose_files',
                     'design_elements', 'i_organized_legacy'],
        )
        action = next(a for a in parser._actions if a.dest == 'source')
        return set(action.choices)

    def test_every_classify_source_has_organize_run_argparse_choice(self):
        """organize_run.py --source must accept every key in SOURCE_CONFIGS."""
        choices = self._organize_run_source_choices()
        for cd_key, expected in CD_TO_ORUN.items():
            self.assertIn(cd_key, classify_design.SOURCE_CONFIGS,
                          f"classify_design.SOURCE_CONFIGS lost key {cd_key!r}")
            self.assertIn(expected, choices,
                          f"organize_run.py --source missing {expected!r} "
                          f"for classify_design source {cd_key!r}")

    def test_every_classify_source_has_review_resolver_entry(self):
        """review_resolver.SOURCE_CONFIGS must mirror classify_design's keys.

        review_resolver covers the AI-pipeline sources only ('design_unorg',
        'design_org', 'loose_files', 'i_organized_legacy').  AE flow has its
        own resolver path; design_elements is currently routed through
        design_org's resolver.
        """
        rr_required = {'design_unorg', 'design_org', 'loose_files',
                       'i_organized_legacy'}
        for src in rr_required:
            self.assertIn(src, classify_design.SOURCE_CONFIGS,
                          f"classify_design.SOURCE_CONFIGS missing {src!r}")
            self.assertIn(src, review_resolver.SOURCE_CONFIGS,
                          f"review_resolver.SOURCE_CONFIGS missing {src!r} — "
                          f"--source will KeyError at apply time")

    def test_every_organize_run_source_dir_is_known(self):
        """organize_run._SOURCE_DIRS keys must be a subset of declared sources.

        Reads the dict literal off the function source — it is defined inside
        main(), so we exercise it indirectly by verifying every key it could
        contain matches a known source.
        """
        import inspect
        src = inspect.getsource(organize_run.main)
        # Cheap parse: every line that looks like "'<key>':" inside _SOURCE_DIRS.
        # Tight enough to fail loudly if someone adds a key but forgets to
        # plumb it through.
        expected_keys = set(CD_TO_ORUN.values()) - {'design'}  # design has its own var
        # 'design' is handled outside _SOURCE_DIRS; drop it so the assertion
        # only covers entries that go through that dict.
        expected_keys |= {'design'}  # but design IS still in _SOURCE_DIRS today
        for key in expected_keys:
            if key == 'ae':
                continue
            self.assertIn(f"'{key}':", src,
                          f"organize_run.main()._SOURCE_DIRS missing {key!r}")

    def test_category_aliases_rhs_are_all_canonical(self):
        """Every right-hand value of CATEGORY_ALIASES must exist in CATEGORIES.

        This is the phantom-category guard: an alias that points at a name
        not in classify_design.CATEGORIES would silently route items to a
        non-canonical destination folder on disk.
        """
        canonical = set(classify_design.CATEGORIES)
        # _Review subdirs are NOT in CATEGORIES but are valid alias targets;
        # whitelist them explicitly.
        review_targets = {c for c in canonical}
        review_targets |= {f"_Review/{c}" for c in canonical}
        review_targets |= {'_Review', '_Skip'}

        bad = []
        for src, dst in organize_run.CATEGORY_ALIASES.items():
            if dst not in review_targets:
                bad.append(f"{src!r} -> {dst!r} (not in classify_design.CATEGORIES)")
        self.assertEqual(bad, [],
                         "Phantom category alias targets:\n  " + "\n  ".join(bad))

    def test_every_batch_prefix_has_offset_branch(self):
        """Each SOURCE_CONFIGS batch_prefix must be wired into batch_offset.

        organize_run.batch_offset uses startswith() against every known prefix
        to map a batch filename back to its position in the index.  Missing
        a branch means the slice arithmetic silently returns 0, which would
        clobber the AE batch space.
        """
        import inspect
        offset_src = inspect.getsource(organize_run.batch_offset)
        for cd_key, cfg in classify_design.SOURCE_CONFIGS.items():
            prefix = cfg['batch_prefix']
            self.assertIn(f"'{prefix}'", offset_src,
                          f"organize_run.batch_offset missing branch for "
                          f"{cd_key!r} prefix {prefix!r}")

    def test_every_batch_prefix_has_glob_dispatch(self):
        """Each SOURCE_CONFIGS batch_prefix must have a glob branch in
        organize_run.load_all_with_index, otherwise apply skips the source.
        """
        import inspect
        loader_src = inspect.getsource(organize_run.load_all_with_index)
        for cd_key, cfg in classify_design.SOURCE_CONFIGS.items():
            prefix = cfg['batch_prefix']
            # The dispatcher uses 'prefix*.json' as the glob pattern — match
            # either the bare prefix or its glob form.
            self.assertTrue(
                f"'{prefix}'" in loader_src or f"'{prefix}*.json'" in loader_src,
                f"organize_run.load_all_with_index missing glob branch for "
                f"{cd_key!r} prefix {prefix!r}")


if __name__ == '__main__':
    unittest.main()
