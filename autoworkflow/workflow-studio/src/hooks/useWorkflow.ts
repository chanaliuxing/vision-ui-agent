// M2: Frontend Studio - Workflow State Management Hook

import { useState, useCallback, useEffect } from 'react';
import {
  WorkflowDefinition,
  StudioState,
  LintResult,
  SimResult,
  ActionRegistry,
  WorkflowStep
} from '@/lib/types';
import { workflowAPI } from '@/lib/api';

// Default empty workflow template
const DEFAULT_WORKFLOW: WorkflowDefinition = {
  name: 'New Workflow',
  description: 'A new workflow',
  version: '1.0.0',
  start: 'step1',
  steps: [
    {
      id: 'step1',
      type: 'action',
      uses: 'ext.open_url',
      params: {
        url: 'https://example.com'
      }
    }
  ],
  edges: [],
  variables: {},
  globals: {
    device_target: 'web'
  }
};

export const useWorkflow = () => {
  const [state, setState] = useState<StudioState>({
    workflow: DEFAULT_WORKFLOW,
    selectedStepId: null,
    isLoading: false,
    isDirty: false
  });

  const [actionRegistry, setActionRegistry] = useState<ActionRegistry>({});

  // Load action registry on mount
  useEffect(() => {
    const loadRegistry = async () => {
      try {
        const registry = await workflowAPI.getActionRegistry();
        setActionRegistry(registry);
      } catch (error) {
        console.error('Failed to load action registry:', error);
      }
    };

    loadRegistry();
  }, []);

  // Update workflow
  const updateWorkflow = useCallback((workflow: WorkflowDefinition) => {
    setState(prev => ({
      ...prev,
      workflow,
      isDirty: true
    }));
  }, []);

  // Update specific step
  const updateStep = useCallback((stepId: string, updates: Partial<WorkflowStep>) => {
    setState(prev => ({
      ...prev,
      workflow: {
        ...prev.workflow,
        steps: prev.workflow.steps.map(step =>
          step.id === stepId ? { ...step, ...updates } : step
        )
      },
      isDirty: true
    }));
  }, []);

  // Add new step
  const addStep = useCallback((step: WorkflowStep) => {
    setState(prev => ({
      ...prev,
      workflow: {
        ...prev.workflow,
        steps: [...prev.workflow.steps, step]
      },
      isDirty: true
    }));
  }, []);

  // Remove step
  const removeStep = useCallback((stepId: string) => {
    setState(prev => ({
      ...prev,
      workflow: {
        ...prev.workflow,
        steps: prev.workflow.steps.filter(step => step.id !== stepId),
        edges: prev.workflow.edges?.filter(edge =>
          edge.from !== stepId && edge.to !== stepId
        ) || []
      },
      selectedStepId: prev.selectedStepId === stepId ? null : prev.selectedStepId,
      isDirty: true
    }));
  }, []);

  // Select step
  const selectStep = useCallback((stepId: string | null) => {
    setState(prev => ({
      ...prev,
      selectedStepId: stepId
    }));
  }, []);

  // Lint workflow
  const lintWorkflow = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true }));

    try {
      const result = await workflowAPI.lintWorkflow(state.workflow);
      setState(prev => ({
        ...prev,
        lintResults: result,
        isLoading: false
      }));
      return result;
    } catch (error) {
      console.error('Lint failed:', error);
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, [state.workflow]);

  // Validate workflow
  const validateWorkflow = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true }));

    try {
      const result = await workflowAPI.validateWorkflow(state.workflow);
      setState(prev => ({ ...prev, isLoading: false }));
      return result;
    } catch (error) {
      console.error('Validation failed:', error);
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, [state.workflow]);

  // Simulate workflow
  const simulateWorkflow = useCallback(async (options?: { debug?: boolean }) => {
    setState(prev => ({ ...prev, isLoading: true }));

    try {
      const result = await workflowAPI.simulateWorkflow(state.workflow, options);
      setState(prev => ({
        ...prev,
        simResults: result,
        isLoading: false
      }));
      return result;
    } catch (error) {
      console.error('Simulation failed:', error);
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, [state.workflow]);

  // Auto-fix workflow
  const autoFixWorkflow = useCallback(async () => {
    if (!state.lintResults?.issues.length) {
      throw new Error('No issues to fix');
    }

    setState(prev => ({ ...prev, isLoading: true }));

    try {
      const result = await workflowAPI.fixWorkflow(state.workflow, state.lintResults.issues);
      setState(prev => ({
        ...prev,
        workflow: result.patched,
        isLoading: false,
        isDirty: true
      }));
      return result;
    } catch (error) {
      console.error('Auto-fix failed:', error);
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, [state.workflow, state.lintResults]);

  // Generate workflow from prompt
  const generateFromPrompt = useCallback(async (prompt: string, options?: {
    complexity?: number;
    allow_actions?: string[];
  }) => {
    setState(prev => ({ ...prev, isLoading: true }));

    try {
      const workflow = await workflowAPI.generateWorkflow(prompt, options);
      setState(prev => ({
        ...prev,
        workflow,
        isLoading: false,
        isDirty: true,
        selectedStepId: null
      }));
      return workflow;
    } catch (error) {
      console.error('Generation failed:', error);
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, []);

  // Load workflow from template
  const loadFromTemplate = useCallback(async (templateId: string, parameters: Record<string, any>) => {
    setState(prev => ({ ...prev, isLoading: true }));

    try {
      const workflow = await workflowAPI.generateFromTemplate(templateId, parameters);
      setState(prev => ({
        ...prev,
        workflow,
        isLoading: false,
        isDirty: true,
        selectedStepId: null
      }));
      return workflow;
    } catch (error) {
      console.error('Template loading failed:', error);
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, []);

  // Reset to clean state
  const resetWorkflow = useCallback((workflow?: WorkflowDefinition) => {
    setState(prev => ({
      ...prev,
      workflow: workflow || DEFAULT_WORKFLOW,
      selectedStepId: null,
      lintResults: undefined,
      simResults: undefined,
      isDirty: false
    }));
  }, []);

  // Get selected step
  const selectedStep = state.selectedStepId
    ? state.workflow.steps.find(step => step.id === state.selectedStepId)
    : null;

  return {
    // State
    workflow: state.workflow,
    selectedStepId: state.selectedStepId,
    selectedStep,
    lintResults: state.lintResults,
    simResults: state.simResults,
    isLoading: state.isLoading,
    isDirty: state.isDirty,
    actionRegistry,

    // Actions
    updateWorkflow,
    updateStep,
    addStep,
    removeStep,
    selectStep,
    lintWorkflow,
    validateWorkflow,
    simulateWorkflow,
    autoFixWorkflow,
    generateFromPrompt,
    loadFromTemplate,
    resetWorkflow
  };
};