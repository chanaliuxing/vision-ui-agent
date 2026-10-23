// M2: Frontend Studio - Auto-Generated Step Editor with RJSF
"use client";

import React, { useMemo, useCallback } from 'react';
import Form from '@rjsf/core';
import { RJSFSchema, UiSchema } from '@rjsf/utils';
import validator from '@rjsf/validator-ajv8';
import type { WorkflowStep, ActionDefinition, ActionRegistry } from '@/lib/types';

interface StepEditorProps {
  step: WorkflowStep | null;
  actionRegistry: ActionRegistry;
  onStepUpdate: (stepId: string, updates: Partial<WorkflowStep>) => void;
  onClose: () => void;
  className?: string;
}

// Default schema for step properties
const baseStepSchema: RJSFSchema = {
  type: 'object',
  properties: {
    id: {
      type: 'string',
      title: 'Step ID',
      description: 'Unique identifier for this step'
    },
    name: {
      type: 'string',
      title: 'Step Name',
      description: 'Human-readable name for this step'
    },
    type: {
      type: 'string',
      title: 'Step Type',
      enum: ['action', 'branch', 'loop', 'parallel', 'wait', 'subflow', 'human_input'],
      description: 'Type of step to execute'
    },
    uses: {
      type: 'string',
      title: 'Action',
      description: 'Action to execute (for action type steps)'
    },
    when: {
      type: 'string',
      title: 'Condition',
      description: 'JavaScript expression to determine if step should run'
    },
    timeout_ms: {
      type: 'number',
      title: 'Timeout (ms)',
      description: 'Maximum execution time in milliseconds',
      minimum: 0
    },
    on_error: {
      type: 'string',
      title: 'Error Handling',
      enum: ['fail', 'skip', 'goto'],
      description: 'How to handle errors in this step'
    },
    goto: {
      type: 'string',
      title: 'Goto Step',
      description: 'Step ID to jump to on error (when on_error is goto)'
    }
  },
  required: ['id', 'type']
};

// UI Schema for better form rendering
const baseUiSchema: UiSchema = {
  id: {
    'ui:disabled': true
  },
  type: {
    'ui:widget': 'select'
  },
  uses: {
    'ui:placeholder': 'Select an action...'
  },
  when: {
    'ui:widget': 'textarea',
    'ui:options': {
      rows: 2
    }
  },
  timeout_ms: {
    'ui:widget': 'updown'
  },
  on_error: {
    'ui:widget': 'select'
  },
  params: {
    'ui:title': 'Parameters'
  },
  retry: {
    times: {
      'ui:widget': 'updown'
    },
    backoff_ms: {
      'ui:widget': 'updown'
    }
  }
};

export const StepEditor: React.FC<StepEditorProps> = ({
  step,
  actionRegistry,
  onStepUpdate,
  onClose,
  className = ''
}) => {
  // Generate dynamic schema based on selected action
  const formSchema = useMemo((): RJSFSchema => {
    if (!step) return baseStepSchema;

    let schema = { ...baseStepSchema };

    // Add action-specific fields
    if (step.type === 'action' && step.uses) {
      const actionDef = actionRegistry[step.uses];
      if (actionDef && actionDef.schema) {
        // Merge action parameters schema
        schema.properties = {
          ...schema.properties,
          params: {
            type: 'object',
            title: 'Parameters',
            description: actionDef.description,
            properties: actionDef.schema.properties || {},
            required: actionDef.schema.required || []
          }
        };
      } else {
        // Generic params for unknown actions
        schema.properties = {
          ...schema.properties,
          params: {
            type: 'object',
            title: 'Parameters',
            description: 'Action parameters (JSON object)',
            additionalProperties: true
          }
        };
      }

      // Add retry configuration
      schema.properties = {
        ...schema.properties,
        retry: {
          type: 'object',
          title: 'Retry Configuration',
          properties: {
            times: {
              type: 'number',
              title: 'Retry Times',
              description: 'Number of retry attempts',
              minimum: 0,
              maximum: 10
            },
            backoff_ms: {
              type: 'number',
              title: 'Backoff (ms)',
              description: 'Delay between retries in milliseconds',
              minimum: 0
            }
          }
        }
      };
    }

    // Add branch-specific fields
    if (step.type === 'branch') {
      schema.properties = {
        ...schema.properties,
        branches: {
          type: 'array',
          title: 'Branches',
          description: 'Conditional branches',
          items: {
            type: 'object',
            properties: {
              condition: {
                type: 'string',
                title: 'Condition',
                description: 'JavaScript expression'
              },
              goto: {
                type: 'string',
                title: 'Target Step',
                description: 'Step ID to jump to'
              }
            },
            required: ['condition', 'goto']
          }
        }
      };
    }

    // Add loop-specific fields
    if (step.type === 'loop') {
      schema.properties = {
        ...schema.properties,
        loop: {
          type: 'object',
          title: 'Loop Configuration',
          properties: {
            condition: {
              type: 'string',
              title: 'Loop Condition',
              description: 'Continue while this expression is true'
            },
            max_iterations: {
              type: 'number',
              title: 'Max Iterations',
              description: 'Maximum number of loop iterations',
              minimum: 1
            }
          },
          required: ['condition']
        }
      };
    }

    return schema;
  }, [step, actionRegistry]);

  // Generate UI schema with action-specific widgets
  const uiSchema = useMemo((): UiSchema => {
    let ui = { ...baseUiSchema };

    if (!step) return ui;

    // Action selection with autocomplete
    if (actionRegistry && Object.keys(actionRegistry).length > 0) {
      ui.uses = {
        ...ui.uses,
        'ui:widget': 'select',
        'ui:enumOptions': Object.keys(actionRegistry).map(key => ({
          value: key,
          label: `${key} - ${actionRegistry[key].title || ''}`
        }))
      };
    }

    return ui;
  }, [step, actionRegistry]);

  // Handle form submission
  const handleSubmit = useCallback(
    (data: any) => {
      if (!step) return;

      const { formData } = data;
      onStepUpdate(step.id, formData);
    },
    [step, onStepUpdate]
  );

  // Handle form changes (live updates)
  const handleChange = useCallback(
    (data: any) => {
      if (!step) return;

      const { formData } = data;
      // Debounced live update could be added here
    },
    [step]
  );

  if (!step) {
    return (
      <div className={`p-6 text-center text-gray-500 ${className}`}>
        <div className="text-lg mb-2">No Step Selected</div>
        <div className="text-sm">
          Select a step from the workflow to edit its properties
        </div>
      </div>
    );
  }

  const actionDef = step.uses ? actionRegistry[step.uses] : null;

  return (
    <div className={`p-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">Edit Step: {step.name || step.id}</h2>
          {actionDef && (
            <p className="text-sm text-gray-600 mt-1">{actionDef.title}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-2 text-gray-400 hover:text-gray-600 rounded"
          title="Close Editor"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Action Info */}
      {actionDef && (
        <div className="mb-6 p-4 bg-blue-50 rounded-lg">
          <div className="text-sm font-medium text-blue-900 mb-2">Action Information</div>
          <div className="text-sm text-blue-800 mb-2">{actionDef.description}</div>
          {actionDef.capabilities && actionDef.capabilities.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {actionDef.capabilities.map((cap, index) => (
                <span
                  key={index}
                  className="px-2 py-1 text-xs bg-blue-200 text-blue-800 rounded"
                >
                  {cap}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Form */}
      <div className="overflow-y-auto max-h-[600px]">
        <Form
          schema={formSchema}
          uiSchema={uiSchema}
          formData={step}
          validator={validator}
          onSubmit={handleSubmit}
          onChange={handleChange}
          showErrorList={false}
          liveValidate={true}
        >
          <div className="flex justify-end space-x-3 mt-6 pt-4 border-t">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded hover:bg-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700"
            >
              Save Changes
            </button>
          </div>
        </Form>
      </div>

      {/* Validation Errors */}
      {actionDef && step.params && (
        <div className="mt-4 text-xs text-gray-500">
          <strong>Required Parameters:</strong>{' '}
          {actionDef.schema?.required?.join(', ') || 'None'}
        </div>
      )}
    </div>
  );
};

export default StepEditor;