import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Alert, AlertDescription } from './ui/alert';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Save, RotateCcw, Copy, Download, AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';

interface WorkflowConfig {
  name: string;
  description: string;
  version: string;
  globalParameters: Record<string, any>;
  steps: any[];
}

interface JsonEditorProps {
  workflow: WorkflowConfig;
  onWorkflowUpdate: (workflow: WorkflowConfig) => void;
}

export function JsonEditor({ workflow, onWorkflowUpdate }: JsonEditorProps) {
  const [jsonText, setJsonText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isValid, setIsValid] = useState(true);
  const [showPretty, setShowPretty] = useState(true);

  useEffect(() => {
    setJsonText(JSON.stringify(workflow, null, showPretty ? 2 : 0));
    setError(null);
    setIsValid(true);
  }, [workflow, showPretty]);

  const validateAndParseJson = (text: string) => {
    try {
      const parsed = JSON.parse(text);
      
      // Validate required fields
      if (!parsed.name || typeof parsed.name !== 'string') {
        throw new Error('Workflow must have a valid name');
      }
      if (!parsed.steps || !Array.isArray(parsed.steps)) {
        throw new Error('Workflow must have a steps array');
      }
      
      // Validate each step
      parsed.steps.forEach((step: any, index: number) => {
        if (!step.id || !step.name || !step.type) {
          throw new Error(`Step ${index + 1} is missing required fields (id, name, type)`);
        }
      });

      return {
        name: parsed.name,
        description: parsed.description || '',
        version: parsed.version || '1.0.0',
        globalParameters: parsed.globalParameters || {},
        steps: parsed.steps
      };
    } catch (err) {
      throw err;
    }
  };

  const handleJsonChange = (value: string) => {
    setJsonText(value);
    setSuccess(false);
    
    try {
      validateAndParseJson(value);
      setError(null);
      setIsValid(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid JSON format');
      setIsValid(false);
    }
  };

  const handleSave = () => {
    try {
      const parsedWorkflow = validateAndParseJson(jsonText);
      onWorkflowUpdate(parsedWorkflow);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid JSON format');
    }
  };

  const handleReset = () => {
    setJsonText(JSON.stringify(workflow, null, showPretty ? 2 : 0));
    setError(null);
    setIsValid(true);
    setSuccess(false);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(jsonText);
      // Could add a toast notification here
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([jsonText], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${workflow.name.toLowerCase().replace(/\s+/g, '-')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const formatJson = () => {
    try {
      const parsed = JSON.parse(jsonText);
      setJsonText(JSON.stringify(parsed, null, 2));
      setShowPretty(true);
    } catch (err) {
      // JSON is invalid, don't format
    }
  };

  const minifyJson = () => {
    try {
      const parsed = JSON.parse(jsonText);
      setJsonText(JSON.stringify(parsed));
      setShowPretty(false);
    } catch (err) {
      // JSON is invalid, don't minify
    }
  };

  const getWorkflowStats = () => {
    try {
      const parsed = JSON.parse(jsonText);
      return {
        steps: parsed.steps?.length || 0,
        globalParams: Object.keys(parsed.globalParameters || {}).length,
        dependencies: parsed.steps?.reduce((acc: number, step: any) => 
          acc + (step.dependencies?.length || 0), 0) || 0
      };
    } catch {
      return { steps: 0, globalParams: 0, dependencies: 0 };
    }
  };

  const stats = getWorkflowStats();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h4>JSON Editor</h4>
          <p className="text-muted-foreground text-sm">
            Edit the workflow configuration directly as JSON
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleCopy}>
            <Copy className="w-4 h-4 mr-2" />
            Copy
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="w-4 h-4 mr-2" />
            Download
          </Button>
          <Button variant="outline" size="sm" onClick={handleReset}>
            <RotateCcw className="w-4 h-4 mr-2" />
            Reset
          </Button>
          <Button onClick={handleSave} disabled={!isValid}>
            <Save className="w-4 h-4 mr-2" />
            Save Changes
          </Button>
        </div>
      </div>

      {/* Workflow Stats */}
      <div className="flex gap-4">
        <Badge variant="outline">{stats.steps} steps</Badge>
        <Badge variant="outline">{stats.globalParams} global parameters</Badge>
        <Badge variant="outline">{stats.dependencies} dependencies</Badge>
        <Badge variant={isValid ? "default" : "destructive"}>
          {isValid ? "Valid JSON" : "Invalid JSON"}
        </Badge>
      </div>

      {/* Formatting Controls */}
      <div className="flex items-center gap-2">
        <Button 
          variant="outline" 
          size="sm" 
          onClick={showPretty ? minifyJson : formatJson}
        >
          {showPretty ? <EyeOff className="w-4 h-4 mr-2" /> : <Eye className="w-4 h-4 mr-2" />}
          {showPretty ? 'Minify' : 'Pretty Print'}
        </Button>
      </div>

      {/* Status Messages */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert>
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>Workflow updated successfully!</AlertDescription>
        </Alert>
      )}

      {/* JSON Editor */}
      <Tabs defaultValue="editor" className="w-full">
        <TabsList>
          <TabsTrigger value="editor">Editor</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>
        
        <TabsContent value="editor">
          <Card className="p-0">
            <Textarea
              value={jsonText}
              onChange={(e) => handleJsonChange(e.target.value)}
              className={`
                min-h-[600px] font-mono text-sm border-0 rounded-lg resize-none
                ${!isValid ? 'border-destructive' : ''}
              `}
              placeholder="Workflow JSON will appear here..."
            />
          </Card>
        </TabsContent>
        
        <TabsContent value="preview">
          <Card className="p-6">
            <div className="space-y-4">
              <h5>Workflow Preview</h5>
              
              {isValid ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <Card className="p-4">
                      <h6 className="text-sm font-medium mb-2">Metadata</h6>
                      <div className="space-y-1 text-sm">
                        <div><strong>Name:</strong> {workflow.name}</div>
                        <div><strong>Version:</strong> {workflow.version}</div>
                        <div><strong>Description:</strong> {workflow.description || 'None'}</div>
                      </div>
                    </Card>
                    
                    <Card className="p-4">
                      <h6 className="text-sm font-medium mb-2">Global Parameters</h6>
                      <div className="space-y-1 text-sm">
                        {Object.keys(workflow.globalParameters).length > 0 ? 
                          Object.entries(workflow.globalParameters).slice(0, 3).map(([key, value]) => (
                            <div key={key}><strong>{key}:</strong> {String(value)}</div>
                          )) :
                          <div className="text-muted-foreground">None configured</div>
                        }
                        {Object.keys(workflow.globalParameters).length > 3 && (
                          <div className="text-muted-foreground">
                            +{Object.keys(workflow.globalParameters).length - 3} more...
                          </div>
                        )}
                      </div>
                    </Card>
                    
                    <Card className="p-4">
                      <h6 className="text-sm font-medium mb-2">Steps</h6>
                      <div className="space-y-1 text-sm">
                        {workflow.steps.slice(0, 3).map((step) => (
                          <div key={step.id}>{step.name} ({step.type})</div>
                        ))}
                        {workflow.steps.length > 3 && (
                          <div className="text-muted-foreground">
                            +{workflow.steps.length - 3} more steps...
                          </div>
                        )}
                      </div>
                    </Card>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <AlertCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Fix JSON errors to see preview</p>
                </div>
              )}
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}