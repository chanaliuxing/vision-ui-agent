import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Card } from './ui/card';
import { WorkflowVisualization } from './WorkflowVisualization';
import { StepConfigPanel } from './StepConfigPanel';
import { GlobalConfigPanel } from './GlobalConfigPanel';
import { JsonEditor } from './JsonEditor';
import { Eye, Settings, Globe, Code } from 'lucide-react';

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

interface WorkflowEditorProps {
  workflow: WorkflowConfig;
  onWorkflowUpdate: (workflow: WorkflowConfig) => void;
}

export function WorkflowEditor({ workflow, onWorkflowUpdate }: WorkflowEditorProps) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('visualization');

  const handleStepUpdate = (stepId: string, updatedStep: WorkflowStep) => {
    const updatedWorkflow = {
      ...workflow,
      steps: workflow.steps.map(step => 
        step.id === stepId ? updatedStep : step
      )
    };
    onWorkflowUpdate(updatedWorkflow);
  };

  const handleStepAdd = (newStep: WorkflowStep) => {
    const updatedWorkflow = {
      ...workflow,
      steps: [...workflow.steps, newStep]
    };
    onWorkflowUpdate(updatedWorkflow);
  };

  const handleStepDelete = (stepId: string) => {
    const updatedWorkflow = {
      ...workflow,
      steps: workflow.steps.filter(step => step.id !== stepId)
    };
    onWorkflowUpdate(updatedWorkflow);
    if (selectedStepId === stepId) {
      setSelectedStepId(null);
    }
  };

  const handleGlobalUpdate = (globalParameters: Record<string, any>) => {
    const updatedWorkflow = {
      ...workflow,
      globalParameters
    };
    onWorkflowUpdate(updatedWorkflow);
  };

  const handleWorkflowMetaUpdate = (name: string, description: string, version: string) => {
    const updatedWorkflow = {
      ...workflow,
      name,
      description,
      version
    };
    onWorkflowUpdate(updatedWorkflow);
  };

  const selectedStep = selectedStepId 
    ? workflow.steps.find(step => step.id === selectedStepId) 
    : null;

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="space-y-2">
          <h2>{workflow.name}</h2>
          <p className="text-muted-foreground">{workflow.description}</p>
          <div className="flex gap-4 text-sm text-muted-foreground">
            <span>Version: {workflow.version}</span>
            <span>Steps: {workflow.steps.length}</span>
          </div>
        </div>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="visualization" className="flex items-center gap-2">
            <Eye className="w-4 h-4" />
            Visualization
          </TabsTrigger>
          <TabsTrigger value="steps" className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            Step Config
          </TabsTrigger>
          <TabsTrigger value="global" className="flex items-center gap-2">
            <Globe className="w-4 h-4" />
            Global Config
          </TabsTrigger>
          <TabsTrigger value="json" className="flex items-center gap-2">
            <Code className="w-4 h-4" />
            JSON Editor
          </TabsTrigger>
        </TabsList>

        <TabsContent value="visualization" className="mt-6">
          <Card className="p-6">
            <WorkflowVisualization
              workflow={workflow}
              selectedStepId={selectedStepId}
              onStepSelect={setSelectedStepId}
              onStepUpdate={handleStepUpdate}
              onStepAdd={handleStepAdd}
              onStepDelete={handleStepDelete}
            />
          </Card>
        </TabsContent>

        <TabsContent value="steps" className="mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-1 p-4">
              <h4 className="mb-4">Workflow Steps</h4>
              <div className="space-y-2">
                {workflow.steps.map((step) => (
                  <div
                    key={step.id}
                    className={`p-3 rounded cursor-pointer transition-colors ${
                      selectedStepId === step.id 
                        ? 'bg-primary text-primary-foreground' 
                        : 'bg-muted hover:bg-muted/80'
                    }`}
                    onClick={() => setSelectedStepId(step.id)}
                  >
                    <div className="font-medium">{step.name}</div>
                    <div className="text-sm opacity-75">{step.type}</div>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="lg:col-span-2 p-6">
              {selectedStep ? (
                <StepConfigPanel
                  step={selectedStep}
                  workflow={workflow}
                  onStepUpdate={(updatedStep) => handleStepUpdate(selectedStep.id, updatedStep)}
                  onStepDelete={() => handleStepDelete(selectedStep.id)}
                />
              ) : (
                <div className="text-center text-muted-foreground py-12">
                  <Settings className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Select a step from the left to configure its parameters</p>
                </div>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="global" className="mt-6">
          <Card className="p-6">
            <GlobalConfigPanel
              workflow={workflow}
              onGlobalUpdate={handleGlobalUpdate}
              onWorkflowMetaUpdate={handleWorkflowMetaUpdate}
            />
          </Card>
        </TabsContent>

        <TabsContent value="json" className="mt-6">
          <Card className="p-6">
            <JsonEditor
              workflow={workflow}
              onWorkflowUpdate={onWorkflowUpdate}
            />
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}