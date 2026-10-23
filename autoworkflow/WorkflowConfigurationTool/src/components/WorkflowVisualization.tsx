import React, { useState } from 'react';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Textarea } from './ui/textarea';
import { Plus, Edit, Trash2, Play, ArrowDown, ArrowRight } from 'lucide-react';

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

interface WorkflowVisualizationProps {
  workflow: WorkflowConfig;
  selectedStepId: string | null;
  onStepSelect: (stepId: string | null) => void;
  onStepUpdate: (stepId: string, step: WorkflowStep) => void;
  onStepAdd: (step: WorkflowStep) => void;
  onStepDelete: (stepId: string) => void;
}

interface NewStepForm {
  name: string;
  type: string;
  description: string;
  dependencies: string[];
}

export function WorkflowVisualization({
  workflow,
  selectedStepId,
  onStepSelect,
  onStepUpdate,
  onStepAdd,
  onStepDelete
}: WorkflowVisualizationProps) {
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newStep, setNewStep] = useState<NewStepForm>({
    name: '',
    type: '',
    description: '',
    dependencies: []
  });

  const stepTypes = [
    'extract', 'transform', 'load', 'validate', 'process', 'deploy', 
    'test', 'notify', 'backup', 'cleanup', 'custom'
  ];

  const handleAddStep = () => {
    if (!newStep.name || !newStep.type) return;

    const step: WorkflowStep = {
      id: `step_${Date.now()}`,
      name: newStep.name,
      type: newStep.type,
      parameters: {
        description: newStep.description || '',
        enabled: true
      },
      dependencies: newStep.dependencies.length > 0 ? newStep.dependencies : undefined
    };

    onStepAdd(step);
    setNewStep({ name: '', type: '', description: '', dependencies: [] });
    setShowAddDialog(false);
  };

  const getStepColor = (type: string) => {
    const colors: Record<string, string> = {
      extract: 'bg-blue-500',
      transform: 'bg-purple-500',
      load: 'bg-green-500',
      validate: 'bg-yellow-500',
      process: 'bg-orange-500',
      deploy: 'bg-red-500',
      test: 'bg-pink-500',
      notify: 'bg-indigo-500',
      backup: 'bg-gray-500',
      cleanup: 'bg-slate-500',
      custom: 'bg-cyan-500'
    };
    return colors[type] || 'bg-gray-500';
  };

  const renderStepConnections = (step: WorkflowStep, index: number) => {
    const hasNextStep = index < workflow.steps.length - 1;
    const hasDependencies = step.dependencies && step.dependencies.length > 0;

    return (
      <div className="flex flex-col items-center">
        {hasDependencies && (
          <div className="text-xs text-muted-foreground mb-2">
            Depends on: {step.dependencies?.join(', ')}
          </div>
        )}
        
        {hasNextStep && (
          <ArrowDown className="w-6 h-6 text-muted-foreground mt-4" />
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3>Workflow Visualization</h3>
        <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="w-4 h-4 mr-2" />
              Add Step
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add New Step</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="step-name">Step Name</Label>
                <Input
                  id="step-name"
                  placeholder="Enter step name"
                  value={newStep.name}
                  onChange={(e) => setNewStep({ ...newStep, name: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="step-type">Step Type</Label>
                <Select value={newStep.type} onValueChange={(value) => setNewStep({ ...newStep, type: value })}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select step type" />
                  </SelectTrigger>
                  <SelectContent>
                    {stepTypes.map((type) => (
                      <SelectItem key={type} value={type}>
                        {type.charAt(0).toUpperCase() + type.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="step-description">Description (Optional)</Label>
                <Textarea
                  id="step-description"
                  placeholder="Describe what this step does"
                  value={newStep.description}
                  onChange={(e) => setNewStep({ ...newStep, description: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label>Dependencies (Optional)</Label>
                <div className="space-y-2">
                  {workflow.steps.map((step) => (
                    <label key={step.id} className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={newStep.dependencies.includes(step.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setNewStep({
                              ...newStep,
                              dependencies: [...newStep.dependencies, step.id]
                            });
                          } else {
                            setNewStep({
                              ...newStep,
                              dependencies: newStep.dependencies.filter(id => id !== step.id)
                            });
                          }
                        }}
                      />
                      <span className="text-sm">{step.name}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex justify-end space-x-2">
                <Button variant="outline" onClick={() => setShowAddDialog(false)}>
                  Cancel
                </Button>
                <Button onClick={handleAddStep} disabled={!newStep.name || !newStep.type}>
                  Add Step
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {workflow.steps.length === 0 ? (
        <Card className="p-12 text-center">
          <div className="space-y-4">
            <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto">
              <Plus className="w-8 h-8 text-muted-foreground" />
            </div>
            <div>
              <h4>No Steps Yet</h4>
              <p className="text-muted-foreground">Add your first step to start building your workflow</p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {workflow.steps.map((step, index) => (
            <div key={step.id} className="flex flex-col items-center">
              <Card
                className={`
                  w-full max-w-md p-4 cursor-pointer transition-all hover:shadow-md
                  ${selectedStepId === step.id ? 'ring-2 ring-primary' : ''}
                `}
                onClick={() => onStepSelect(step.id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className={`w-3 h-3 rounded-full ${getStepColor(step.type)}`} />
                    <div>
                      <h4 className="text-sm">{step.name}</h4>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="secondary" className="text-xs">
                          {step.type}
                        </Badge>
                        {step.dependencies && step.dependencies.length > 0 && (
                          <Badge variant="outline" className="text-xs">
                            {step.dependencies.length} dependencies
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        onStepSelect(step.id);
                      }}
                    >
                      <Edit className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        onStepDelete(step.id);
                      }}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                {Object.keys(step.parameters).length > 0 && (
                  <div className="mt-3 pt-3 border-t">
                    <div className="text-xs text-muted-foreground">
                      {Object.keys(step.parameters).length} parameter(s) configured
                    </div>
                  </div>
                )}
              </Card>
              
              {renderStepConnections(step, index)}
            </div>
          ))}

          <div className="text-center pt-6">
            <Button 
              variant="outline" 
              className="gap-2"
              onClick={() => setShowAddDialog(true)}
            >
              <Plus className="w-4 h-4" />
              Add Another Step
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}