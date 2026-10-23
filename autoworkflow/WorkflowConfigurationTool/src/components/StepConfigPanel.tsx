import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Switch } from './ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Trash2, Plus, Save, RotateCcw } from 'lucide-react';
import { Separator } from './ui/separator';

interface WorkflowStep {
  id: string;
  name: string;
  type: string;
  parameters: Record<string, any>;
  dependencies?: string[];
}

interface WorkflowConfig {
  name: string;
  description: string;
  version: string;
  globalParameters: Record<string, any>;
  steps: WorkflowStep[];
}

interface StepConfigPanelProps {
  step: WorkflowStep;
  workflow: WorkflowConfig;
  onStepUpdate: (step: WorkflowStep) => void;
  onStepDelete: () => void;
}

interface ParameterValue {
  value: any;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
}

export function StepConfigPanel({ step, workflow, onStepUpdate, onStepDelete }: StepConfigPanelProps) {
  const [editedStep, setEditedStep] = useState<WorkflowStep>(step);
  const [newParamKey, setNewParamKey] = useState('');
  const [newParamValue, setNewParamValue] = useState('');
  const [newParamType, setNewParamType] = useState<ParameterValue['type']>('string');

  useEffect(() => {
    setEditedStep(step);
  }, [step]);

  const handleSave = () => {
    onStepUpdate(editedStep);
  };

  const handleReset = () => {
    setEditedStep(step);
  };

  const handleParameterUpdate = (key: string, value: any) => {
    setEditedStep({
      ...editedStep,
      parameters: {
        ...editedStep.parameters,
        [key]: value
      }
    });
  };

  const handleParameterDelete = (key: string) => {
    const newParams = { ...editedStep.parameters };
    delete newParams[key];
    setEditedStep({
      ...editedStep,
      parameters: newParams
    });
  };

  const addParameter = () => {
    if (!newParamKey.trim()) return;

    let processedValue = newParamValue;
    try {
      switch (newParamType) {
        case 'number':
          processedValue = parseFloat(newParamValue) || 0;
          break;
        case 'boolean':
          processedValue = newParamValue.toLowerCase() === 'true';
          break;
        case 'array':
          processedValue = newParamValue.split(',').map(v => v.trim());
          break;
        case 'object':
          processedValue = JSON.parse(newParamValue || '{}');
          break;
        default:
          processedValue = newParamValue;
      }
    } catch (error) {
      processedValue = newParamValue;
    }

    handleParameterUpdate(newParamKey, processedValue);
    setNewParamKey('');
    setNewParamValue('');
    setNewParamType('string');
  };

  const handleDependencyToggle = (stepId: string) => {
    const currentDeps = editedStep.dependencies || [];
    const newDeps = currentDeps.includes(stepId)
      ? currentDeps.filter(id => id !== stepId)
      : [...currentDeps, stepId];
    
    setEditedStep({
      ...editedStep,
      dependencies: newDeps.length > 0 ? newDeps : undefined
    });
  };

  const renderParameterInput = (key: string, value: any) => {
    const type = typeof value;
    
    if (type === 'boolean') {
      return (
        <Switch
          checked={value}
          onCheckedChange={(checked) => handleParameterUpdate(key, checked)}
        />
      );
    }
    
    if (type === 'number') {
      return (
        <Input
          type="number"
          value={value}
          onChange={(e) => handleParameterUpdate(key, parseFloat(e.target.value) || 0)}
        />
      );
    }
    
    if (type === 'object' && Array.isArray(value)) {
      return (
        <Textarea
          value={value.join(', ')}
          onChange={(e) => handleParameterUpdate(key, e.target.value.split(',').map(v => v.trim()))}
          placeholder="Enter comma-separated values"
        />
      );
    }
    
    if (type === 'object') {
      return (
        <Textarea
          value={JSON.stringify(value, null, 2)}
          onChange={(e) => {
            try {
              handleParameterUpdate(key, JSON.parse(e.target.value));
            } catch (error) {
              // Invalid JSON, don't update
            }
          }}
          rows={4}
        />
      );
    }
    
    return (
      <Input
        value={value}
        onChange={(e) => handleParameterUpdate(key, e.target.value)}
      />
    );
  };

  const getParameterTypeBadge = (value: any) => {
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    return 'string';
  };

  const availableDependencies = workflow.steps.filter(s => s.id !== step.id);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h4>Configure Step: {step.name}</h4>
          <Badge variant="secondary">{step.type}</Badge>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleReset}>
            <RotateCcw className="w-4 h-4 mr-2" />
            Reset
          </Button>
          <Button onClick={handleSave}>
            <Save className="w-4 h-4 mr-2" />
            Save Changes
          </Button>
          <Button variant="destructive" onClick={onStepDelete}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="step-name">Step Name</Label>
          <Input
            id="step-name"
            value={editedStep.name}
            onChange={(e) => setEditedStep({ ...editedStep, name: e.target.value })}
          />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="step-type">Step Type</Label>
          <Input
            id="step-type"
            value={editedStep.type}
            onChange={(e) => setEditedStep({ ...editedStep, type: e.target.value })}
          />
        </div>
      </div>

      <Separator />

      <div className="space-y-4">
        <h5>Dependencies</h5>
        <div className="space-y-2">
          {availableDependencies.length > 0 ? (
            availableDependencies.map((availableStep) => (
              <label key={availableStep.id} className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={(editedStep.dependencies || []).includes(availableStep.id)}
                  onChange={() => handleDependencyToggle(availableStep.id)}
                />
                <span>{availableStep.name}</span>
                <Badge variant="outline" className="text-xs">{availableStep.type}</Badge>
              </label>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">No other steps available for dependencies</p>
          )}
        </div>
      </div>

      <Separator />

      <div className="space-y-4">
        <h5>Parameters</h5>
        
        <div className="space-y-3">
          {Object.entries(editedStep.parameters).map(([key, value]) => (
            <Card key={key} className="p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Label className="text-sm font-medium">{key}</Label>
                  <Badge variant="outline" className="text-xs">
                    {getParameterTypeBadge(value)}
                  </Badge>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleParameterDelete(key)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
              {renderParameterInput(key, value)}
            </Card>
          ))}
        </div>

        <Card className="p-4 bg-muted/50">
          <h6 className="mb-3">Add New Parameter</h6>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
            <Input
              placeholder="Parameter name"
              value={newParamKey}
              onChange={(e) => setNewParamKey(e.target.value)}
            />
            <Select value={newParamType} onValueChange={(value: ParameterValue['type']) => setNewParamType(value)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="string">String</SelectItem>
                <SelectItem value="number">Number</SelectItem>
                <SelectItem value="boolean">Boolean</SelectItem>
                <SelectItem value="array">Array</SelectItem>
                <SelectItem value="object">Object</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="Value"
              value={newParamValue}
              onChange={(e) => setNewParamValue(e.target.value)}
            />
            <Button onClick={addParameter} disabled={!newParamKey.trim()}>
              <Plus className="w-4 h-4" />
            </Button>
          </div>
          <div className="text-xs text-muted-foreground mt-2">
            {newParamType === 'array' && 'Enter comma-separated values'}
            {newParamType === 'object' && 'Enter valid JSON'}
            {newParamType === 'boolean' && 'Enter "true" or "false"'}
          </div>
        </Card>
      </div>
    </div>
  );
}