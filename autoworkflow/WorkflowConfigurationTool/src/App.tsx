import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Card } from './components/ui/card';
import { WorkflowUpload } from './components/WorkflowUpload';
import { AiWorkflowCreator } from './components/AiWorkflowCreator';
import { WorkflowEditor } from './components/WorkflowEditor';
import { Upload, Bot, Settings, FileText } from 'lucide-react';

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

export default function App() {
  const [workflow, setWorkflow] = useState<WorkflowConfig | null>(null);
  const [activeTab, setActiveTab] = useState("upload");

  const handleWorkflowLoad = (loadedWorkflow: WorkflowConfig) => {
    setWorkflow(loadedWorkflow);
    setActiveTab("editor");
  };

  const handleWorkflowCreate = (createdWorkflow: WorkflowConfig) => {
    setWorkflow(createdWorkflow);
    setActiveTab("editor");
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto p-6">
        <div className="mb-8">
          <h1 className="mb-2">Workflow Configuration Tool</h1>
          <p className="text-muted-foreground">
            Upload existing workflows, create new ones with AI, and configure all parameters
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="upload" className="flex items-center gap-2">
              <Upload className="w-4 h-4" />
              Upload Workflow
            </TabsTrigger>
            <TabsTrigger value="ai-create" className="flex items-center gap-2">
              <Bot className="w-4 h-4" />
              AI Creator
            </TabsTrigger>
            <TabsTrigger value="editor" disabled={!workflow} className="flex items-center gap-2">
              <Settings className="w-4 h-4" />
              Configure Workflow
            </TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="mt-6">
            <Card className="p-6">
              <WorkflowUpload onWorkflowLoad={handleWorkflowLoad} />
            </Card>
          </TabsContent>

          <TabsContent value="ai-create" className="mt-6">
            <Card className="p-6">
              <AiWorkflowCreator onWorkflowCreate={handleWorkflowCreate} />
            </Card>
          </TabsContent>

          <TabsContent value="editor" className="mt-6">
            {workflow && (
              <WorkflowEditor 
                workflow={workflow} 
                onWorkflowUpdate={setWorkflow} 
              />
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}