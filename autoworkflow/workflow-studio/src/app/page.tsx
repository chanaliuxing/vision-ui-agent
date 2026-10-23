// M2: Frontend Studio - Main Page
"use client";

import React, { useState } from 'react';
import { useWorkflow } from '@/hooks/useWorkflow';
import JsonEditor from '@/components/JsonEditor';
import WorkflowDAG from '@/components/WorkflowDAG';
import StepEditor from '@/components/StepEditor';
import IssuesPanel from '@/components/IssuesPanel';
import SimulationResults from '@/components/SimulationResults';
import type { WorkflowEdge, LintIssue } from '@/lib/types';

export default function WorkflowStudio() {
  const {
    workflow,
    selectedStep,
    selectedStepId,
    lintResults,
    simResults,
    isLoading,
    isDirty,
    actionRegistry,
    updateWorkflow,
    updateStep,
    selectStep,
    lintWorkflow,
    simulateWorkflow,
    autoFixWorkflow,
    generateFromPrompt,
    resetWorkflow
  } = useWorkflow();

  const [activeTab, setActiveTab] = useState<'dag' | 'json'>('dag');
  const [rightPanel, setRightPanel] = useState<'step' | 'issues' | 'simulation'>('step');
  const [generatePrompt, setGeneratePrompt] = useState('');

  // Handle DAG operations
  const handleEdgeAdd = (edge: WorkflowEdge) => {
    const newEdges = [...(workflow.edges || []), edge];
    updateWorkflow({ ...workflow, edges: newEdges });
  };

  const handleEdgeRemove = (edgeId: string) => {
    const newEdges = (workflow.edges || []).filter(edge =>
      `edge-${edge.from}-${edge.to}` !== edgeId
    );
    updateWorkflow({ ...workflow, edges: newEdges });
  };

  // Handle issue click
  const handleIssueClick = (issue: LintIssue) => {
    if (issue.pointer) {
      // Try to extract step ID from JSON pointer
      const match = issue.pointer.match(/\/steps\/(\d+)/);
      if (match) {
        const stepIndex = parseInt(match[1]);
        const step = workflow.steps?.[stepIndex];
        if (step) {
          selectStep(step.id);
          setRightPanel('step');
        }
      }
    }
  };

  // Handle AI generation
  const handleGenerate = async () => {
    if (!generatePrompt.trim()) return;

    try {
      await generateFromPrompt(generatePrompt);
      setGeneratePrompt('');
    } catch (error) {
      console.error('Generation failed:', error);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <h1 className="text-xl font-bold text-gray-900">Workflow Studio</h1>
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-600">{workflow.name}</span>
            <span className="text-xs text-gray-400">v{workflow.version}</span>
            {isDirty && (
              <span className="w-2 h-2 bg-orange-400 rounded-full" title="Unsaved changes" />
            )}
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* AI Generation */}
          <div className="flex items-center space-x-2">
            <input
              type="text"
              placeholder="Describe workflow to generate..."
              value={generatePrompt}
              onChange={(e) => setGeneratePrompt(e.target.value)}
              className="px-3 py-1 text-sm border rounded w-64"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleGenerate();
                }
              }}
            />
            <button
              onClick={handleGenerate}
              disabled={!generatePrompt.trim() || isLoading}
              className="px-3 py-1 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:bg-gray-400"
            >
              🤖 Generate
            </button>
          </div>

          {/* Actions */}
          <button
            onClick={lintWorkflow}
            disabled={isLoading}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
          >
            🔍 Lint
          </button>
          <button
            onClick={() => simulateWorkflow()}
            disabled={isLoading}
            className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400"
          >
            ▶️ Simulate
          </button>
          <button
            onClick={() => resetWorkflow()}
            className="px-3 py-1 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
          >
            🔄 Reset
          </button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - Editor */}
        <div className="w-1/2 bg-white border-r flex flex-col">
          {/* Tab Header */}
          <div className="border-b px-4 py-2 flex items-center space-x-4">
            <button
              onClick={() => setActiveTab('dag')}
              className={`px-3 py-1 text-sm rounded ${
                activeTab === 'dag'
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              📊 Visual Editor
            </button>
            <button
              onClick={() => setActiveTab('json')}
              className={`px-3 py-1 text-sm rounded ${
                activeTab === 'json'
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              📝 JSON Editor
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'dag' ? (
              <WorkflowDAG
                workflow={workflow}
                selectedStepId={selectedStepId}
                onStepSelect={selectStep}
                onStepUpdate={updateStep}
                onEdgeAdd={handleEdgeAdd}
                onEdgeRemove={handleEdgeRemove}
                className="h-full"
              />
            ) : (
              <JsonEditor
                value={workflow}
                onChange={updateWorkflow}
                height="100%"
                className="h-full"
              />
            )}
          </div>
        </div>

        {/* Right Panel */}
        <div className="w-1/2 bg-white flex flex-col">
          {/* Tab Header */}
          <div className="border-b px-4 py-2 flex items-center space-x-4">
            <button
              onClick={() => setRightPanel('step')}
              className={`px-3 py-1 text-sm rounded ${
                rightPanel === 'step'
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              ⚙️ Step Editor
            </button>
            <button
              onClick={() => setRightPanel('issues')}
              className={`px-3 py-1 text-sm rounded relative ${
                rightPanel === 'issues'
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              🐛 Issues
              {lintResults && lintResults.summary.total > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                  {lintResults.summary.total}
                </span>
              )}
            </button>
            <button
              onClick={() => setRightPanel('simulation')}
              className={`px-3 py-1 text-sm rounded ${
                rightPanel === 'simulation'
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              🎮 Simulation
            </button>
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-hidden">
            {rightPanel === 'step' && (
              <StepEditor
                step={selectedStep}
                actionRegistry={actionRegistry}
                onStepUpdate={updateStep}
                onClose={() => selectStep(null)}
                className="h-full"
              />
            )}
            {rightPanel === 'issues' && (
              <IssuesPanel
                lintResults={lintResults}
                onIssueClick={handleIssueClick}
                onAutoFix={autoFixWorkflow}
                isAutoFixing={isLoading}
                className="h-full"
              />
            )}
            {rightPanel === 'simulation' && (
              <SimulationResults
                simResults={simResults}
                onRerun={() => simulateWorkflow()}
                isRunning={isLoading}
                className="h-full"
              />
            )}
          </div>
        </div>
      </div>

      {/* Loading Overlay */}
      {isLoading && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg shadow-lg">
            <div className="flex items-center space-x-3">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              <span className="text-lg">Processing...</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
