// M2: Frontend Studio - Simulation Results Display
"use client";

import React, { useState } from 'react';
import type { SimResult } from '@/lib/types';

interface SimulationResultsProps {
  simResults?: SimResult;
  onRerun?: () => void;
  isRunning?: boolean;
  className?: string;
}

const TraceStep: React.FC<{
  step: any;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}> = ({ step, index, isExpanded, onToggle }) => {
  const hasError = step.error || step.status === 'failed';
  const isSuccess = step.status === 'completed' || step.status === 'success';

  return (
    <div className={`
      border rounded-lg mb-2 overflow-hidden
      ${hasError ? 'border-red-300 bg-red-50' :
        isSuccess ? 'border-green-300 bg-green-50' :
        'border-gray-300 bg-white'}
    `}>
      {/* Header */}
      <div
        className="p-3 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="text-sm font-mono text-gray-500">
              #{index + 1}
            </span>
            <span className="font-medium">
              {step.step_id || step.action || 'Unknown Step'}
            </span>
            <span className={`
              px-2 py-1 text-xs rounded-full
              ${hasError ? 'bg-red-100 text-red-800' :
                isSuccess ? 'bg-green-100 text-green-800' :
                'bg-gray-100 text-gray-800'}
            `}>
              {step.status || 'unknown'}
            </span>
          </div>
          <div className="flex items-center space-x-2">
            {step.duration_ms && (
              <span className="text-xs text-gray-500">
                {step.duration_ms}ms
              </span>
            )}
            <svg
              className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t p-3 bg-white">
          {/* Input/Parameters */}
          {step.input && (
            <div className="mb-3">
              <div className="text-sm font-medium text-gray-700 mb-1">Input:</div>
              <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto">
                {JSON.stringify(step.input, null, 2)}
              </pre>
            </div>
          )}

          {/* Output */}
          {step.output && (
            <div className="mb-3">
              <div className="text-sm font-medium text-gray-700 mb-1">Output:</div>
              <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto">
                {JSON.stringify(step.output, null, 2)}
              </pre>
            </div>
          )}

          {/* Error Details */}
          {step.error && (
            <div className="mb-3">
              <div className="text-sm font-medium text-red-700 mb-1">Error:</div>
              <div className="text-sm text-red-800 bg-red-100 p-2 rounded">
                {typeof step.error === 'string' ? step.error : JSON.stringify(step.error, null, 2)}
              </div>
            </div>
          )}

          {/* Context/State */}
          {step.context && (
            <div className="mb-3">
              <div className="text-sm font-medium text-gray-700 mb-1">Context:</div>
              <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto max-h-32">
                {JSON.stringify(step.context, null, 2)}
              </pre>
            </div>
          )}

          {/* Metadata */}
          <div className="text-xs text-gray-500 space-y-1">
            {step.timestamp && (
              <div>Timestamp: {new Date(step.timestamp).toLocaleString()}</div>
            )}
            {step.step_type && (
              <div>Type: {step.step_type}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export const SimulationResults: React.FC<SimulationResultsProps> = ({
  simResults,
  onRerun,
  isRunning = false,
  className = ''
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const toggleStep = (index: number) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedSteps(newExpanded);
  };

  const expandAll = () => {
    if (simResults?.trace) {
      setExpandedSteps(new Set(simResults.trace.map((_, i) => i)));
    }
  };

  const collapseAll = () => {
    setExpandedSteps(new Set());
  };

  if (!simResults) {
    return (
      <div className={`p-6 text-center text-gray-500 ${className}`}>
        <div className="text-lg mb-2">No Simulation Results</div>
        <div className="text-sm">
          Run a simulation to see the execution trace
        </div>
        {onRerun && (
          <button
            onClick={onRerun}
            disabled={isRunning}
            className={`
              mt-4 px-4 py-2 text-sm rounded transition-colors
              ${isRunning
                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
              }
            `}
          >
            {isRunning ? 'Running...' : '▶️ Run Simulation'}
          </button>
        )}
      </div>
    );
  }

  const { success, trace, final_state, error, debug } = simResults;
  const hasSteps = trace && trace.length > 0;

  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="p-4 border-b bg-gray-50">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold">Simulation Results</h3>
          <div className="flex items-center space-x-2">
            {hasSteps && (
              <>
                <button
                  onClick={expandAll}
                  className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                >
                  Expand All
                </button>
                <button
                  onClick={collapseAll}
                  className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                >
                  Collapse All
                </button>
              </>
            )}
            {onRerun && (
              <button
                onClick={onRerun}
                disabled={isRunning}
                className={`
                  px-3 py-1 text-sm rounded transition-colors
                  ${isRunning
                    ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                    : 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                  }
                `}
              >
                {isRunning ? 'Running...' : '🔄 Rerun'}
              </button>
            )}
          </div>
        </div>

        {/* Status */}
        <div className="flex items-center space-x-4">
          <span className={`
            px-3 py-1 text-sm rounded-full font-medium
            ${success
              ? 'bg-green-100 text-green-800'
              : 'bg-red-100 text-red-800'
            }
          `}>
            {success ? '✅ Success' : '❌ Failed'}
          </span>
          {hasSteps && (
            <span className="text-sm text-gray-600">
              {trace.length} step{trace.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Main Error */}
      {error && (
        <div className="p-4 bg-red-50 border-l-4 border-red-400">
          <div className="text-sm font-medium text-red-800 mb-1">Simulation Error:</div>
          <div className="text-sm text-red-700">{error}</div>
        </div>
      )}

      {/* Execution Trace */}
      <div className="flex-1 overflow-y-auto p-4">
        {hasSteps ? (
          <div className="space-y-2">
            {trace.map((step, index) => (
              <TraceStep
                key={index}
                step={step}
                index={index}
                isExpanded={expandedSteps.has(index)}
                onToggle={() => toggleStep(index)}
              />
            ))}
          </div>
        ) : (
          <div className="text-center text-gray-500 py-8">
            <div className="text-lg mb-1">No Execution Trace</div>
            <div className="text-sm">The simulation completed without generating trace data</div>
          </div>
        )}
      </div>

      {/* Final State */}
      {final_state && (
        <div className="border-t p-4 bg-gray-50">
          <div className="text-sm font-medium text-gray-700 mb-2">Final State:</div>
          <pre className="text-xs bg-white p-3 rounded border overflow-x-auto max-h-32">
            {JSON.stringify(final_state, null, 2)}
          </pre>
        </div>
      )}

      {/* Debug Info */}
      {debug && debug.length > 0 && (
        <div className="border-t p-4 bg-blue-50">
          <div className="text-sm font-medium text-blue-700 mb-2">Debug Information:</div>
          <div className="space-y-1">
            {debug.map((item, index) => (
              <div key={index} className="text-xs bg-white p-2 rounded border">
                {typeof item === 'string' ? item : JSON.stringify(item, null, 2)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SimulationResults;