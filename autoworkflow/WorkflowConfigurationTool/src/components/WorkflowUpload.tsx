import React, { useCallback, useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Alert, AlertDescription } from './ui/alert';
import { Card } from './ui/card';
import { Upload, FileText, CheckCircle, AlertCircle } from 'lucide-react';

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

interface WorkflowUploadProps {
  onWorkflowLoad: (workflow: WorkflowConfig) => void;
}

export function WorkflowUpload({ onWorkflowLoad }: WorkflowUploadProps) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const validateWorkflow = (data: any): WorkflowConfig => {
    if (!data.name || typeof data.name !== 'string') {
      throw new Error('Workflow must have a valid name');
    }
    if (!data.steps || !Array.isArray(data.steps)) {
      throw new Error('Workflow must have a steps array');
    }
    
    // Validate each step
    data.steps.forEach((step: any, index: number) => {
      if (!step.id || !step.name || !step.type) {
        throw new Error(`Step ${index + 1} is missing required fields (id, name, type)`);
      }
    });

    return {
      name: data.name,
      description: data.description || '',
      version: data.version || '1.0.0',
      globalParameters: data.globalParameters || {},
      steps: data.steps
    };
  };

  const processFile = useCallback((file: File) => {
    setError(null);
    setSuccess(false);

    if (!file.name.endsWith('.json')) {
      setError('Please upload a JSON file');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const data = JSON.parse(content);
        const workflow = validateWorkflow(data);
        
        setSuccess(true);
        setTimeout(() => {
          onWorkflowLoad(workflow);
        }, 1000);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Invalid JSON format');
      }
    };
    reader.readAsText(file);
  }, [onWorkflowLoad]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      processFile(files[0]);
    }
  }, [processFile]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2">Upload Workflow JSON</h3>
        <p className="text-muted-foreground">
          Upload an existing workflow configuration file to start editing
        </p>
      </div>

      <Card
        className={`
          border-2 border-dashed p-8 text-center transition-colors cursor-pointer
          ${dragOver ? 'border-primary bg-primary/5' : 'border-border'}
          ${success ? 'border-green-500 bg-green-50 dark:bg-green-950' : ''}
        `}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        {success ? (
          <div className="space-y-4">
            <CheckCircle className="w-12 h-12 text-green-500 mx-auto" />
            <div>
              <h4 className="text-green-700 dark:text-green-300">Workflow Loaded Successfully!</h4>
              <p className="text-green-600 dark:text-green-400">Redirecting to editor...</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <Upload className="w-12 h-12 text-muted-foreground mx-auto" />
            <div>
              <h4>Drop your workflow JSON file here</h4>
              <p className="text-muted-foreground">or click to browse files</p>
            </div>
            <Input
              type="file"
              accept=".json"
              onChange={handleFileInput}
              className="max-w-xs mx-auto cursor-pointer"
            />
          </div>
        )}
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-4">
        <h4>Example Workflow Structure</h4>
        <Card className="p-4 bg-muted">
          <pre className="text-sm overflow-x-auto">
{JSON.stringify({
  "name": "Data Processing Pipeline",
  "description": "A sample workflow for data processing",
  "version": "1.0.0",
  "globalParameters": {
    "timeout": 300,
    "retries": 3
  },
  "steps": [
    {
      "id": "step1",
      "name": "Data Extraction",
      "type": "extract",
      "parameters": {
        "source": "database",
        "query": "SELECT * FROM users"
      }
    },
    {
      "id": "step2", 
      "name": "Data Transformation",
      "type": "transform",
      "parameters": {
        "operations": ["clean", "normalize"]
      },
      "dependencies": ["step1"]
    }
  ]
}, null, 2)}
          </pre>
        </Card>
      </div>
    </div>
  );
}