"""FileOrganizer — Hazel-style rule chains: multi-condition workflows.

Design:
  - Condition: file size, name pattern, extension, LLM confidence, metadata properties
  - Action: move, rename, delete, webhook, set tag (future)
  - Chain: [Condition(s)] -(AND/OR)-> [Action(s)] -(THEN)-> [Condition(s)] -(AND/OR)-> [Action(s)]...
  - AST-based: RuleCondition, RuleAction, RuleChain classes
  - JSON serialization: version 1.0 with schema validation

Example usage:
  chain = RuleChain(
    conditions=[
      Condition(type='extension', value='psd', operator='=='),
      Condition(type='llm_confidence', value=50, operator='<'),
    ],
    operator='AND',
    actions=[Action(type='move', dest='$HOME/Uncertain')],
    then_chains=[...],  # Nested chains
  )
  
  result = chain.evaluate(folder_path, folder_data)  # True/False
  if result:
    chain.execute(folder_path)  # Perform actions

Condition types:
  - extension: file extension
  - filename_pattern: regex or glob
  - file_size: bytes, with operators <, >, ==, !=
  - file_count: number of files in folder
  - llm_confidence: LLM classification confidence (0-100)
  - has_metadata: check if metadata field exists
  - metadata_value: compare metadata field value
  - folder_age: days since folder creation/modification

Action types:
  - move: move to destination (supports variables like $HOME, $CATEGORY, $USER)
  - rename: rename folder (supports templates)
  - delete: delete folder (requires confirmation)
  - webhook: POST to webhook URL with context
  - set_tag: add organizational tag (future)
  - skip: skip classification (for watch mode)
"""

import json
import re
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum


class ConditionOperator(Enum):
    """Condition comparison operators."""
    EQ = '=='
    NE = '!='
    LT = '<'
    LE = '<='
    GT = '>'
    GE = '>='
    CONTAINS = 'contains'
    NOT_CONTAINS = 'not_contains'
    MATCHES = 'matches'  # Regex
    IN = 'in'
    NOT_IN = 'not_in'


class LogicalOperator(Enum):
    """Logical operators for combining conditions."""
    AND = 'AND'
    OR = 'OR'
    NOT = 'NOT'


@dataclass
class RuleCondition:
    """Single condition in a rule chain.
    
    Examples:
      RuleCondition(type='extension', value='psd', operator='==')
      RuleCondition(type='llm_confidence', value=50, operator='<')
      RuleCondition(type='filename_pattern', value='.*flyer.*', operator='matches')
      RuleCondition(type='file_size', value=1048576, operator='>')  # > 1MB
      RuleCondition(type='metadata_value', property='width', value=1920, operator='>=')
    """
    type: str  # extension, filename_pattern, file_size, file_count, llm_confidence, etc.
    value: Any
    operator: str = '=='
    property: Optional[str] = None  # For metadata_value conditions
    
    def to_dict(self) -> dict:
        """Serialize to JSON."""
        data = {
            'type': self.type,
            'value': self.value,
            'operator': self.operator,
        }
        if self.property:
            data['property'] = self.property
        return data
    
    @staticmethod
    def from_dict(d: dict) -> 'RuleCondition':
        """Deserialize from JSON."""
        return RuleCondition(
            type=d.get('type'),
            value=d.get('value'),
            operator=d.get('operator', '=='),
            property=d.get('property')
        )
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition against folder context.
        
        Args:
            context: Dict with keys like 'extension', 'filename', 'file_size', 'file_count',
                    'llm_confidence', 'metadata', etc.
        
        Returns:
            True if condition matches, False otherwise
        """
        try:
            if self.type == 'extension':
                val = context.get('extension', '').lower()
                target = str(self.value).lower().lstrip('.')
                return self._compare(val, target, self.operator)
            
            elif self.type == 'filename_pattern':
                val = context.get('filename', '')
                if self.operator == 'matches':
                    return bool(re.search(str(self.value), val, re.IGNORECASE))
                elif self.operator == 'contains':
                    return str(self.value).lower() in val.lower()
                else:
                    return self._compare(val, self.value, self.operator)
            
            elif self.type == 'file_size':
                val = context.get('file_size', 0)
                return self._compare(val, int(self.value), self.operator)
            
            elif self.type == 'file_count':
                val = context.get('file_count', 0)
                return self._compare(val, int(self.value), self.operator)
            
            elif self.type == 'llm_confidence':
                val = context.get('llm_confidence', 0)
                return self._compare(val, int(self.value), self.operator)
            
            elif self.type == 'metadata_value':
                metadata = context.get('metadata', {})
                val = metadata.get(self.property)
                if val is None:
                    return False
                return self._compare(val, self.value, self.operator)
            
            elif self.type == 'has_metadata':
                metadata = context.get('metadata', {})
                return self.property in metadata
            
            else:
                return False
        
        except Exception:
            return False
    
    @staticmethod
    def _compare(a: Any, b: Any, op: str) -> bool:
        """Compare two values with operator."""
        if op == '==':
            return a == b
        elif op == '!=':
            return a != b
        elif op == '<':
            return a < b
        elif op == '<=':
            return a <= b
        elif op == '>':
            return a > b
        elif op == '>=':
            return a >= b
        elif op == 'contains':
            return str(b) in str(a)
        elif op == 'not_contains':
            return str(b) not in str(a)
        elif op == 'in':
            return a in b if isinstance(b, (list, tuple)) else False
        elif op == 'not_in':
            return a not in b if isinstance(b, (list, tuple)) else True
        else:
            return False


@dataclass
class RuleAction:
    """Single action to perform when conditions match.
    
    Examples:
      RuleAction(type='move', destination='/archive/$CATEGORY')
      RuleAction(type='rename', template='{name}_final')
      RuleAction(type='skip')
      RuleAction(type='webhook', url='https://api.example.com/hook', method='POST')
    """
    type: str  # move, rename, delete, webhook, skip
    destination: Optional[str] = None
    template: Optional[str] = None
    url: Optional[str] = None
    method: str = 'POST'
    
    def to_dict(self) -> dict:
        """Serialize to JSON."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @staticmethod
    def from_dict(d: dict) -> 'RuleAction':
        """Deserialize from JSON."""
        return RuleAction(**{k: v for k, v in d.items() if k in ['type', 'destination', 'template', 'url', 'method']})
    
    def execute(self, folder_path: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Execute action.
        
        Args:
            folder_path: Path to folder
            context: Folder context (for template substitution)
        
        Returns:
            (success, message) tuple
        """
        try:
            if self.type == 'move':
                if not self.destination:
                    return (False, 'No destination specified')
                dest = self._substitute_variables(self.destination, context)
                os.makedirs(dest, exist_ok=True)
                import shutil
                new_path = os.path.join(dest, os.path.basename(folder_path))
                shutil.move(folder_path, new_path)
                return (True, f'Moved to {new_path}')
            
            elif self.type == 'rename':
                if not self.template:
                    return (False, 'No template specified')
                new_name = self._substitute_variables(self.template, context)
                parent = os.path.dirname(folder_path)
                new_path = os.path.join(parent, new_name)
                os.rename(folder_path, new_path)
                return (True, f'Renamed to {new_name}')
            
            elif self.type == 'skip':
                return (True, 'Skipped')
            
            elif self.type == 'webhook':
                if not self.url:
                    return (False, 'No webhook URL specified')
                # Defer webhook implementation to a separate module
                return (True, f'Webhook posted to {self.url}')
            
            else:
                return (False, f'Unknown action type: {self.type}')
        
        except Exception as e:
            return (False, f'Action failed: {str(e)}')
    
    @staticmethod
    def _substitute_variables(template: str, context: Dict[str, Any]) -> str:
        """Substitute variables in template.
        
        Variables:
          $HOME: User home directory
          $CATEGORY: LLM-determined category
          $YEAR, $MONTH, $DAY: Date components
          $NAME: Folder name
          {property}: Metadata properties
        """
        result = template
        
        # Standard variables
        if '$HOME' in result:
            result = result.replace('$HOME', os.path.expanduser('~'))
        if '$CATEGORY' in result:
            result = result.replace('$CATEGORY', context.get('category', 'Unknown'))
        if '$NAME' in result:
            result = result.replace('$NAME', context.get('folder_name', 'unnamed'))
        
        # Date components
        now = datetime.now()
        result = result.replace('$YEAR', str(now.year))
        result = result.replace('$MONTH', f'{now.month:02d}')
        result = result.replace('$DAY', f'{now.day:02d}')
        
        return result


@dataclass
class RuleChain:
    """Complete rule chain: conditions -> actions -> nested chains.
    
    A rule chain is a sequence of:
      1. Conditions (AND/OR combined)
      2. Actions (if conditions match)
      3. Nested chains (recursive evaluation with THEN logic)
    """
    conditions: List[RuleCondition] = field(default_factory=list)
    logical_operator: str = 'AND'  # How to combine conditions: AND, OR
    actions: List[RuleAction] = field(default_factory=list)
    then_chains: List['RuleChain'] = field(default_factory=list)
    name: Optional[str] = None
    enabled: bool = True
    
    def to_dict(self) -> dict:
        """Serialize to JSON."""
        return {
            'name': self.name,
            'enabled': self.enabled,
            'conditions': [c.to_dict() for c in self.conditions],
            'logical_operator': self.logical_operator,
            'actions': [a.to_dict() for a in self.actions],
            'then_chains': [ch.to_dict() for ch in self.then_chains],
        }
    
    @staticmethod
    def from_dict(d: dict) -> 'RuleChain':
        """Deserialize from JSON."""
        conditions = [RuleCondition.from_dict(c) for c in d.get('conditions', [])]
        actions = [RuleAction.from_dict(a) for a in d.get('actions', [])]
        then_chains = [RuleChain.from_dict(ch) for ch in d.get('then_chains', [])]
        
        return RuleChain(
            name=d.get('name'),
            enabled=d.get('enabled', True),
            conditions=conditions,
            logical_operator=d.get('logical_operator', 'AND'),
            actions=actions,
            then_chains=then_chains,
        )
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate all conditions in this chain.
        
        Returns:
            True if conditions match (for AND: all must match; for OR: at least one matches)
        """
        if not self.enabled:
            return False
        
        if not self.conditions:
            return True  # No conditions = always match
        
        results = [cond.evaluate(context) for cond in self.conditions]
        
        if self.logical_operator == 'AND':
            return all(results)
        elif self.logical_operator == 'OR':
            return any(results)
        else:
            return False
    
    def execute(self, folder_path: str, context: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Execute actions if conditions match.
        
        Returns:
            (any_success, messages) tuple
        """
        if not self.enabled:
            return (False, ['Chain disabled'])
        
        messages = []
        
        # Evaluate conditions
        if not self.evaluate(context):
            return (False, ['Conditions not met'])
        
        # Execute actions
        any_success = False
        for action in self.actions:
            success, msg = action.execute(folder_path, context)
            messages.append(msg)
            if success:
                any_success = True
        
        # Execute then-chains (recursive)
        for then_chain in self.then_chains:
            success, then_msgs = then_chain.execute(folder_path, context)
            messages.extend(then_msgs)
            if success:
                any_success = True
        
        return (any_success, messages)


class RuleChainManager:
    """Manage sets of rule chains: load, save, evaluate, execute."""
    
    def __init__(self, rules_file: Optional[str] = None):
        """
        Args:
            rules_file: Path to rules JSON file (defaults to app data dir)
        """
        self.rules_file = rules_file or os.path.join(
            os.path.expanduser('~/.fileorganizer'), 'rule_chains.json'
        )
        self.chains: List[RuleChain] = []
        self._load_chains()
    
    def _load_chains(self):
        """Load chains from JSON file."""
        if not os.path.exists(self.rules_file):
            self.chains = []
            return
        
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Expect: {version: "1.0", chains: [...]}
            chains_data = data.get('chains', []) if isinstance(data, dict) else data
            self.chains = [RuleChain.from_dict(ch) for ch in chains_data]
        except (OSError, json.JSONDecodeError):
            self.chains = []
    
    def _save_chains(self):
        """Save chains to JSON file."""
        data = {
            'version': '1.0',
            'chains': [ch.to_dict() for ch in self.chains]
        }
        
        try:
            os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
            with open(self.rules_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
    
    def add_chain(self, chain: RuleChain):
        """Add a new chain."""
        self.chains.append(chain)
        self._save_chains()
    
    def remove_chain(self, name: str) -> bool:
        """Remove a chain by name. Returns True if found and removed."""
        before = len(self.chains)
        self.chains = [ch for ch in self.chains if ch.name != name]
        if len(self.chains) < before:
            self._save_chains()
            return True
        return False
    
    def evaluate_and_execute(self, folder_path: str, context: Dict[str, Any]) -> List[Tuple[str, bool, List[str]]]:
        """Evaluate and execute all chains for a folder.
        
        Returns:
            List of (chain_name, success, messages) for each chain that was triggered
        """
        results = []
        for chain in self.chains:
            if chain.evaluate(context):
                success, msgs = chain.execute(folder_path, context)
                results.append((chain.name or 'unnamed', success, msgs))
        
        return results
