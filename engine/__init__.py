"""Chameleon layout engine.

Pipeline: analyze.py reads roles from geometry -> layout.py builds candidate
layouts -> score.py scores each -> chameleon.py picks the best and writes the
report. textfit.py measures text with the renderer's fonts; resize.py is the
entry point the starter's main.py calls.
"""
