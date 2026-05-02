"""Tests for Hazel-style rule chains."""

import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path

from fileorganizer.rule_chains import (
    RuleCondition, RuleAction, RuleChain, RuleChainManager
)


@pytest.fixture
def temp_rules_file():
    """Create a temporary rules file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    yield temp_path
    try:
        os.remove(temp_path)
    except OSError:
        pass


@pytest.fixture
def temp_lib_dir():
    """Create a temporary library directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_rule_condition_extension():
    """Test extension condition."""
    cond = RuleCondition(type='extension', value='psd', operator='==')
    
    # Should match
    context = {'extension': 'psd', 'filename': 'design.psd', 'file_size': 1024}
    assert cond.evaluate(context) is True
    
    # Should not match
    context = {'extension': 'ai', 'filename': 'design.ai', 'file_size': 1024}
    assert cond.evaluate(context) is False


def test_rule_condition_file_size():
    """Test file size condition."""
    cond = RuleCondition(type='file_size', value=1048576, operator='>')  # > 1MB
    
    context = {'file_size': 2097152}  # 2MB
    assert cond.evaluate(context) is True
    
    context = {'file_size': 524288}  # 512KB
    assert cond.evaluate(context) is False


def test_rule_condition_llm_confidence():
    """Test LLM confidence condition."""
    cond = RuleCondition(type='llm_confidence', value=70, operator='<')
    
    context = {'llm_confidence': 50}
    assert cond.evaluate(context) is True
    
    context = {'llm_confidence': 85}
    assert cond.evaluate(context) is False


def test_rule_condition_filename_pattern():
    """Test filename pattern condition."""
    cond = RuleCondition(type='filename_pattern', value='.*flyer.*', operator='matches')
    
    context = {'filename': 'summer_flyer_2025'}
    assert cond.evaluate(context) is True
    
    context = {'filename': 'logo_design'}
    assert cond.evaluate(context) is False


def test_rule_condition_metadata_value():
    """Test metadata value condition."""
    cond = RuleCondition(type='metadata_value', property='width', value=1920, operator='>=')
    
    context = {'metadata': {'width': 2560}}
    assert cond.evaluate(context) is True
    
    context = {'metadata': {'width': 1024}}
    assert cond.evaluate(context) is False


def test_rule_condition_has_metadata():
    """Test metadata existence condition."""
    cond = RuleCondition(type='has_metadata', property='author')
    
    context = {'metadata': {'author': 'John', 'year': 2025}}
    assert cond.evaluate(context) is True
    
    context = {'metadata': {'year': 2025}}
    assert cond.evaluate(context) is False


def test_rule_condition_serialization():
    """Test condition to_dict and from_dict."""
    cond = RuleCondition(type='file_size', value=1048576, operator='>')
    
    data = cond.to_dict()
    restored = RuleCondition.from_dict(data)
    
    assert restored.type == cond.type
    assert restored.value == cond.value
    assert restored.operator == cond.operator


def test_rule_action_move(temp_lib_dir):
    """Test move action."""
    # Create source folder
    src = os.path.join(temp_lib_dir, 'source')
    os.makedirs(src, exist_ok=True)
    Path(os.path.join(src, 'test.txt')).touch()
    
    # Create destination
    dest_dir = os.path.join(temp_lib_dir, 'archive')
    os.makedirs(dest_dir, exist_ok=True)
    
    action = RuleAction(type='move', destination=dest_dir)
    context = {'folder_name': 'source', 'category': 'Design'}
    
    success, msg = action.execute(src, context)
    
    assert success is True
    assert os.path.exists(os.path.join(dest_dir, 'source'))
    assert not os.path.exists(src)


def test_rule_action_rename(temp_lib_dir):
    """Test rename action."""
    # Create source folder
    src = os.path.join(temp_lib_dir, 'original')
    os.makedirs(src, exist_ok=True)
    
    action = RuleAction(type='rename', template='renamed_final')
    context = {'folder_name': 'original'}
    
    success, msg = action.execute(src, context)
    
    assert success is True
    expected = os.path.join(temp_lib_dir, 'renamed_final')
    assert os.path.exists(expected)


def test_rule_action_skip():
    """Test skip action."""
    action = RuleAction(type='skip')
    success, msg = action.execute('/fake/path', {})
    
    assert success is True
    assert 'Skipped' in msg


def test_rule_action_variable_substitution():
    """Test variable substitution in action templates."""
    # Test $HOME substitution
    template = '$HOME/Archive/$CATEGORY/$NAME'
    context = {'folder_name': 'MyProject', 'category': 'Design'}
    
    result = RuleAction._substitute_variables(template, context)
    
    assert '$HOME' not in result
    assert 'Design' in result
    assert 'MyProject' in result


def test_rule_chain_and_conditions():
    """Test rule chain with AND conditions."""
    chain = RuleChain(
        conditions=[
            RuleCondition(type='extension', value='psd', operator='=='),
            RuleCondition(type='llm_confidence', value=70, operator='<'),
        ],
        logical_operator='AND'
    )
    
    # Should match: both conditions true
    context = {'extension': 'psd', 'llm_confidence': 50}
    assert chain.evaluate(context) is True
    
    # Should not match: only one condition true
    context = {'extension': 'psd', 'llm_confidence': 85}
    assert chain.evaluate(context) is False


def test_rule_chain_or_conditions():
    """Test rule chain with OR conditions."""
    chain = RuleChain(
        conditions=[
            RuleCondition(type='extension', value='psd', operator='=='),
            RuleCondition(type='extension', value='ai', operator='=='),
        ],
        logical_operator='OR'
    )
    
    # Should match: one condition true
    context = {'extension': 'psd'}
    assert chain.evaluate(context) is True
    
    context = {'extension': 'ai'}
    assert chain.evaluate(context) is True
    
    # Should not match: no conditions true
    context = {'extension': 'svg'}
    assert chain.evaluate(context) is False


def test_rule_chain_disabled():
    """Test that disabled chains don't execute."""
    chain = RuleChain(
        conditions=[RuleCondition(type='extension', value='psd', operator='==')],
        actions=[RuleAction(type='skip')],
        enabled=False
    )
    
    context = {'extension': 'psd'}
    assert chain.evaluate(context) is False


def test_rule_chain_serialization():
    """Test chain serialization."""
    chain = RuleChain(
        name='psd_uncertain',
        enabled=True,
        conditions=[RuleCondition(type='llm_confidence', value=70, operator='<')],
        actions=[RuleAction(type='skip')],
    )
    
    data = chain.to_dict()
    restored = RuleChain.from_dict(data)
    
    assert restored.name == chain.name
    assert restored.enabled == chain.enabled
    assert len(restored.conditions) == 1
    assert len(restored.actions) == 1


def test_rule_chain_nested():
    """Test nested chains (THEN logic)."""
    inner_chain = RuleChain(
        conditions=[RuleCondition(type='extension', value='ai', operator='==')],
        actions=[RuleAction(type='skip')]
    )
    
    outer_chain = RuleChain(
        conditions=[RuleCondition(type='llm_confidence', value=70, operator='<')],
        actions=[RuleAction(type='skip')],
        then_chains=[inner_chain]
    )
    
    # Outer condition matches, should evaluate inner
    context = {'llm_confidence': 50, 'extension': 'ai'}
    assert outer_chain.evaluate(context) is True


def test_rule_chain_manager_add_and_save(temp_rules_file):
    """Test adding chains and saving to file."""
    manager = RuleChainManager(rules_file=temp_rules_file)
    
    chain = RuleChain(
        name='test_chain',
        conditions=[RuleCondition(type='extension', value='psd', operator='==')],
        actions=[RuleAction(type='skip')]
    )
    
    manager.add_chain(chain)
    assert len(manager.chains) == 1
    
    # Verify saved to file
    with open(temp_rules_file, 'r') as f:
        data = json.load(f)
    assert len(data['chains']) == 1


def test_rule_chain_manager_load_from_file(temp_rules_file):
    """Test loading chains from file."""
    # Create a rules file with data
    rules_data = {
        'version': '1.0',
        'chains': [
            {
                'name': 'test_chain',
                'enabled': True,
                'conditions': [
                    {'type': 'extension', 'value': 'psd', 'operator': '=='}
                ],
                'logical_operator': 'AND',
                'actions': [{'type': 'skip'}],
                'then_chains': []
            }
        ]
    }
    
    with open(temp_rules_file, 'w') as f:
        json.dump(rules_data, f)
    
    # Load and verify
    manager = RuleChainManager(rules_file=temp_rules_file)
    assert len(manager.chains) == 1
    assert manager.chains[0].name == 'test_chain'


def test_rule_chain_manager_remove_chain(temp_rules_file):
    """Test removing a chain."""
    manager = RuleChainManager(rules_file=temp_rules_file)
    
    chain = RuleChain(name='to_remove', enabled=True)
    manager.add_chain(chain)
    assert len(manager.chains) == 1
    
    removed = manager.remove_chain('to_remove')
    assert removed is True
    assert len(manager.chains) == 0
    
    # Verify not in file
    with open(temp_rules_file, 'r') as f:
        data = json.load(f)
    assert len(data['chains']) == 0


def test_rule_chain_manager_evaluate_and_execute(temp_rules_file):
    """Test evaluating and executing chains for a folder."""
    manager = RuleChainManager(rules_file=temp_rules_file)
    
    chain1 = RuleChain(
        name='low_confidence',
        conditions=[RuleCondition(type='llm_confidence', value=70, operator='<')],
        actions=[RuleAction(type='skip')]
    )
    
    chain2 = RuleChain(
        name='high_confidence',
        conditions=[RuleCondition(type='llm_confidence', value=85, operator='>=')],
        actions=[RuleAction(type='skip')]
    )
    
    manager.add_chain(chain1)
    manager.add_chain(chain2)
    
    # Context with low confidence
    context = {'llm_confidence': 50}
    results = manager.evaluate_and_execute('/fake/path', context)
    
    # Should match only chain1
    assert len(results) == 1
    assert results[0][0] == 'low_confidence'
    assert results[0][1] is True  # Success


def test_rule_condition_operators():
    """Test various comparison operators."""
    test_cases = [
        (RuleCondition(type='file_size', value=100, operator='<'), {'file_size': 50}, True),
        (RuleCondition(type='file_size', value=100, operator='<'), {'file_size': 150}, False),
        (RuleCondition(type='file_size', value=100, operator='>='), {'file_size': 100}, True),
        (RuleCondition(type='extension', value='psd', operator='!='), {'extension': 'ai'}, True),
    ]
    
    for cond, context, expected in test_cases:
        assert cond.evaluate(context) == expected, f"Failed for {cond.operator}"
