import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Switch } from './ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Trash2, Plus, Save, RotateCcw, Download } from 'lucide-react';
import { Separator } from './ui/separator';

interface WorkflowConfig {
  name: string;
  description: string;
  version: string;
  globalParameters: Record<string, any>;
  steps: any[];
}

interface GlobalConfigPanelProps {
  workflow: WorkflowConfig;
  onGlobalUpdate: (globalParameters: Record<string, any>) => void;
  onWorkflowMetaUpdate: (name: string, description: string, version: string) => void;
}

interface ParameterValue {
  value: any;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
}

export function GlobalConfigPanel({ 
  workflow, 
  onGlobalUpdate, 
  onWorkflowMetaUpdate 
}: GlobalConfigPanelProps) {
  const [editedMeta, setEditedMeta] = useState({
    name: workflow.name,
    description: workflow.description,
    version: workflow.version
  });
  
  const [editedGlobals, setEditedGlobals] = useState(workflow.globalParameters);
  const [newParamKey, setNewParamKey] = useState('');
  const [newParamValue, setNewParamValue] = useState('');
  const [newParamType, setNewParamType] = useState<ParameterValue['type']>('string');

  useEffect(() => {
    setEditedMeta({
      name: workflow.name,
      description: workflow.description,
      version: workflow.version
    });
    setEditedGlobals(workflow.globalParameters);
  }, [workflow]);

  const handleSave = () => {
    onWorkflowMetaUpdate(editedMeta.name, editedMeta.description, editedMeta.version);
    onGlobalUpdate(editedGlobals);
  };

  const handleReset = () => {
    setEditedMeta({
      name: workflow.name,
      description: workflow.description,
      version: workflow.version
    });
    setEditedGlobals(workflow.globalParameters);
  };

  const handleGlobalParameterUpdate = (key: string, value: any) => {
    setEditedGlobals({
      ...editedGlobals,
      [key]: value
    });
  };

  const handleGlobalParameterDelete = (key: string) => {
    const newParams = { ...editedGlobals };
    delete newParams[key];
    setEditedGlobals(newParams);
  };

  const addGlobalParameter = () => {
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

    handleGlobalParameterUpdate(newParamKey, processedValue);
    setNewParamKey('');
    setNewParamValue('');
    setNewParamType('string');
  };

  const renderParameterInput = (key: string, value: any) => {
    const type = typeof value;
    
    if (type === 'boolean') {
      return (
        <Switch
          checked={value}
          onCheckedChange={(checked) => handleGlobalParameterUpdate(key, checked)}
        />
      );
    }
    
    if (type === 'number') {
      return (
        <Input
          type="number"
          value={value}
          onChange={(e) => handleGlobalParameterUpdate(key, parseFloat(e.target.value) || 0)}
        />
      );
    }
    
    if (type === 'object' && Array.isArray(value)) {
      return (
        <Textarea
          value={value.join(', ')}
          onChange={(e) => handleGlobalParameterUpdate(key, e.target.value.split(',').map(v => v.trim()))}
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
              handleGlobalParameterUpdate(key, JSON.parse(e.target.value));
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
        onChange={(e) => handleGlobalParameterUpdate(key, e.target.value)}
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

  const handleExport = () => {
    const workflowToExport = {
      ...workflow,
      name: editedMeta.name,
      description: editedMeta.description,
      version: editedMeta.version,
      globalParameters: editedGlobals
    };

    const blob = new Blob([JSON.stringify(workflowToExport, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${workflowToExport.name.toLowerCase().replace(/\s+/g, '-')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const commonGlobalParams = [
    { key: 'timeout', value: 300, type: 'number' as const, description: 'Default timeout in seconds' },
    { key: 'retries', value: 3, type: 'number' as const, description: 'Number of retry attempts' },
    { key: 'parallel', value: false, type: 'boolean' as const, description: 'Enable parallel execution' },
    { key: 'logLevel', value: 'info', type: 'string' as const, description: 'Logging level' },
    { key: 'environment', value: 'production', type: 'string' as const, description: 'Target environment' },
    { key: 'notifications', value: true, type: 'boolean' as const, description: 'Enable notifications' }
  ];

  const addCommonParameter = (param: typeof commonGlobalParams[0]) => {
    if (!(param.key in editedGlobals)) {
      handleGlobalParameterUpdate(param.key, param.value);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h4>Global Configuration</h4>
          <p className="text-muted-foreground text-sm">
            Configure workflow metadata and global parameters that apply to all steps
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleExport}>
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
          <Button variant="outline" onClick={handleReset}>
            <RotateCcw className="w-4 h-4 mr-2" />
            Reset
          </Button>
          <Button onClick={handleSave}>
            <Save className="w-4 h-4 mr-2" />
            Save Changes
          </Button>
        </div>
      </div>

      {/* Workflow Metadata */}
      <Card className="p-6">
        <h5 className="mb-4">Workflow Metadata</h5>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="workflow-name">Workflow Name</Label>
            <Input
              id="workflow-name"
              value={editedMeta.name}
              onChange={(e) => setEditedMeta({ ...editedMeta, name: e.target.value })}
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="workflow-version">Version</Label>
            <Input
              id="workflow-version"
              value={editedMeta.version}
              onChange={(e) => setEditedMeta({ ...editedMeta, version: e.target.value })}
            />
          </div>
        </div>
        
        <div className="space-y-2 mt-4">
          <Label htmlFor="workflow-description">Description</Label>
          <Textarea
            id="workflow-description"
            value={editedMeta.description}
            onChange={(e) => setEditedMeta({ ...editedMeta, description: e.target.value })}
            rows={3}
          />
        </div>
      </Card>

      <Separator />

      {/* Global Parameters */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h5>Global Parameters</h5>
          <p className="text-sm text-muted-foreground">
            {Object.keys(editedGlobals).length} parameter(s) configured
          </p>
        </div>
        
        {/* Common Parameters Quick Add */}
        <Card className="p-4 bg-muted/50">
          <h6 className="mb-3">Quick Add Common Parameters</h6>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {commonGlobalParams.map((param) => (
              <Button
                key={param.key}
                variant="outline"
                size="sm"
                onClick={() => addCommonParameter(param)}
                disabled={param.key in editedGlobals}
                className="justify-start text-left"
              >
                <div>
                  <div className="font-medium">{param.key}</div>
                  <div className="text-xs text-muted-foreground">{param.description}</div>
                </div>
              </Button>
            ))}
          </div>
        </Card>

        {/* Existing Parameters */}
        <div className="space-y-3">
          {Object.entries(editedGlobals).map(([key, value]) => (
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
                  onClick={() => handleGlobalParameterDelete(key)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
              {renderParameterInput(key, value)}
            </Card>
          ))}
        </div>

        {/* Add New Parameter */}
        <Card className="p-4 bg-muted/50">
          <h6 className="mb-3">Add Custom Parameter</h6>
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
            <Button onClick={addGlobalParameter} disabled={!newParamKey.trim()}>
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