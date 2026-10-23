import React, { useState } from 'react';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card } from './ui/card';
import { Loader2, Sparkles, FileText } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

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

interface AiWorkflowCreatorProps {
  onWorkflowCreate: (workflow: WorkflowConfig) => void;
}

export function AiWorkflowCreator({ onWorkflowCreate }: AiWorkflowCreatorProps) {
  const [prompt, setPrompt] = useState('');
  const [workflowType, setWorkflowType] = useState('');
  const [complexity, setComplexity] = useState('medium');
  const [loading, setLoading] = useState(false);
  const [generatedWorkflow, setGeneratedWorkflow] = useState<WorkflowConfig | null>(null);

  const workflowTemplates = {
    'data-pipeline': 'Data Processing Pipeline',
    'ml-training': 'Machine Learning Training',
    'api-integration': 'API Integration',
    'deployment': 'Deployment Pipeline',
    'testing': 'Testing Workflow',
    'custom': 'Custom Workflow'
  };

  const generateWorkflow = async () => {
    setLoading(true);
    
    // Simulate AI generation with mock data
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    const workflow: WorkflowConfig = createMockWorkflow(prompt, workflowType, complexity);
    setGeneratedWorkflow(workflow);
    setLoading(false);
  };

  const createMockWorkflow = (prompt: string, type: string, complexity: string): WorkflowConfig => {
    const baseSteps = getBaseStepsForType(type);
    const complexityMultiplier = complexity === 'simple' ? 0.5 : complexity === 'complex' ? 2 : 1;
    
    const steps = baseSteps.slice(0, Math.max(2, Math.floor(baseSteps.length * complexityMultiplier)));
    
    return {
      name: prompt || `${workflowTemplates[type as keyof typeof workflowTemplates] || 'Generated Workflow'}`,
      description: `AI-generated workflow based on: "${prompt}"`,
      version: '1.0.0',
      globalParameters: {
        timeout: 300,
        retries: 3,
        parallel: complexity === 'complex',
        logLevel: 'info'
      },
      steps: steps.map((step, index) => ({
        ...step,
        id: `step_${index + 1}`,
        dependencies: index > 0 ? [`step_${index}`] : undefined
      }))
    };
  };

  const getBaseStepsForType = (type: string): Omit<WorkflowStep, 'id'>[] => {
    switch (type) {
      case 'data-pipeline':
        return [
          { name: 'Data Extraction', type: 'extract', parameters: { source: 'database', format: 'json' } },
          { name: 'Data Validation', type: 'validate', parameters: { schema: 'user_schema.json' } },
          { name: 'Data Transformation', type: 'transform', parameters: { operations: ['clean', 'normalize'] } },
          { name: 'Data Loading', type: 'load', parameters: { destination: 'warehouse', batch_size: 1000 } }
        ];
      case 'ml-training':
        return [
          { name: 'Data Preparation', type: 'prepare', parameters: { split_ratio: 0.8, features: ['all'] } },
          { name: 'Model Training', type: 'train', parameters: { algorithm: 'random_forest', epochs: 100 } },
          { name: 'Model Evaluation', type: 'evaluate', parameters: { metrics: ['accuracy', 'f1_score'] } },
          { name: 'Model Deployment', type: 'deploy', parameters: { environment: 'staging' } }
        ];
      case 'api-integration':
        return [
          { name: 'API Authentication', type: 'auth', parameters: { method: 'oauth2', scope: 'read_write' } },
          { name: 'Data Fetch', type: 'fetch', parameters: { endpoint: '/api/v1/data', pagination: true } },
          { name: 'Data Processing', type: 'process', parameters: { format: 'json', validate: true } },
          { name: 'Response Formatting', type: 'format', parameters: { output_format: 'csv' } }
        ];
      default:
        return [
          { name: 'Initialize', type: 'init', parameters: { setup: 'default' } },
          { name: 'Process', type: 'process', parameters: { mode: 'standard' } },
          { name: 'Finalize', type: 'finalize', parameters: { cleanup: true } }
        ];
    }
  };

  const handleUseWorkflow = () => {
    if (generatedWorkflow) {
      onWorkflowCreate(generatedWorkflow);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2">AI Workflow Creator</h3>
        <p className="text-muted-foreground">
          Describe your workflow requirements and let AI generate a configuration for you
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="workflow-type">Workflow Type</Label>
          <Select value={workflowType} onValueChange={setWorkflowType}>
            <SelectTrigger>
              <SelectValue placeholder="Select workflow type" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(workflowTemplates).map(([key, value]) => (
                <SelectItem key={key} value={key}>{value}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="complexity">Complexity Level</Label>
          <Select value={complexity} onValueChange={setComplexity}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="simple">Simple (2-3 steps)</SelectItem>
              <SelectItem value="medium">Medium (4-6 steps)</SelectItem>
              <SelectItem value="complex">Complex (6+ steps)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="prompt">Workflow Description</Label>
        <Textarea
          id="prompt"
          placeholder="Describe what you want your workflow to do... e.g., 'Process customer data from CSV files, validate emails, and send to CRM system'"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
        />
      </div>

      <Button 
        onClick={generateWorkflow} 
        disabled={loading || !prompt.trim() || !workflowType}
        className="w-full"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Generating Workflow...
          </>
        ) : (
          <>
            <Sparkles className="w-4 h-4 mr-2" />
            Generate Workflow
          </>
        )}
      </Button>

      {generatedWorkflow && (
        <Card className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Generated Workflow
            </h4>
            <Button onClick={handleUseWorkflow}>Use This Workflow</Button>
          </div>
          
          <div className="space-y-2">
            <p><strong>Name:</strong> {generatedWorkflow.name}</p>
            <p><strong>Description:</strong> {generatedWorkflow.description}</p>
            <p><strong>Steps:</strong> {generatedWorkflow.steps.length}</p>
          </div>

          <div className="space-y-2">
            <h5>Steps Preview:</h5>
            <div className="grid gap-2">
              {generatedWorkflow.steps.map((step, index) => (
                <div key={step.id} className="flex items-center gap-2 p-2 bg-muted rounded">
                  <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm">
                    {index + 1}
                  </div>
                  <span>{step.name}</span>
                  <span className="text-xs bg-secondary px-2 py-1 rounded">{step.type}</span>
                </div>
              ))}
            </div>
          </div>

          <details className="space-y-2">
            <summary className="cursor-pointer hover:text-primary">View Full JSON</summary>
            <pre className="text-xs bg-muted p-4 rounded overflow-x-auto">
              {JSON.stringify(generatedWorkflow, null, 2)}
            </pre>
          </details>
        </Card>
      )}
    </div>
  );
}