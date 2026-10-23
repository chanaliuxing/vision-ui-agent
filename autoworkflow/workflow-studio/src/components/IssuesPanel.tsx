// M2: Frontend Studio - Issues Panel for Lint Results
"use client";

import React, { useState } from 'react';
import type { LintResult, LintIssue } from '@/lib/types';

interface IssuesPanelProps {
  lintResults?: LintResult;
  onIssueClick?: (issue: LintIssue) => void;
  onAutoFix?: () => void;
  isAutoFixing?: boolean;
  className?: string;
}

const severityColors = {
  error: 'text-red-800 bg-red-100 border-red-300',
  warn: 'text-yellow-800 bg-yellow-100 border-yellow-300',
  info: 'text-blue-800 bg-blue-100 border-blue-300'
};

const severityIcons = {
  error: '❌',
  warn: '⚠️',
  info: 'ℹ️'
};

const IssueItem: React.FC<{
  issue: LintIssue;
  onClick?: (issue: LintIssue) => void;
}> = ({ issue, onClick }) => {
  return (
    <div
      className={`
        p-3 border-l-4 mb-2 cursor-pointer hover:shadow-sm transition-shadow
        ${severityColors[issue.level]}
      `}
      onClick={() => onClick?.(issue)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-1">
            <span className="text-sm">{severityIcons[issue.level]}</span>
            <span className="font-mono text-xs bg-gray-200 px-2 py-1 rounded">
              {issue.code}
            </span>
            <span className="text-xs uppercase font-medium">
              {issue.level}
            </span>
          </div>
          <div className="text-sm font-medium mb-1">{issue.message}</div>
          {issue.pointer && (
            <div className="text-xs text-gray-600 font-mono">
              Location: {issue.pointer}
            </div>
          )}
          {issue.fix && (
            <div className="mt-2 p-2 bg-gray-50 rounded text-xs">
              <div className="font-medium text-gray-700 mb-1">
                Suggested Fix ({issue.fix.type}):
              </div>
              <div className="text-gray-600">{issue.fix.description}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const IssuesPanel: React.FC<IssuesPanelProps> = ({
  lintResults,
  onIssueClick,
  onAutoFix,
  isAutoFixing = false,
  className = ''
}) => {
  const [filter, setFilter] = useState<'all' | 'error' | 'warn' | 'info'>('all');

  if (!lintResults) {
    return (
      <div className={`p-6 text-center text-gray-500 ${className}`}>
        <div className="text-lg mb-2">No Lint Results</div>
        <div className="text-sm">
          Run the linter to see workflow issues and suggestions
        </div>
      </div>
    );
  }

  const { issues, summary } = lintResults;
  const filteredIssues = filter === 'all'
    ? issues
    : issues.filter(issue => issue.level === filter);

  const hasFixableIssues = issues.some(issue => issue.fix);

  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="p-4 border-b bg-gray-50">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold">Issues & Suggestions</h3>
          {hasFixableIssues && (
            <button
              onClick={onAutoFix}
              disabled={isAutoFixing}
              className={`
                px-3 py-1 text-sm rounded transition-colors
                ${isAutoFixing
                  ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                  : 'bg-green-100 text-green-800 hover:bg-green-200'
                }
              `}
            >
              {isAutoFixing ? 'Fixing...' : '🔧 Auto Fix'}
            </button>
          )}
        </div>

        {/* Summary */}
        <div className="flex items-center space-x-4 text-sm mb-3">
          <span className="text-gray-600">
            Total: {summary.total}
          </span>
          <span className="text-red-600">
            Errors: {summary.errors}
          </span>
          <span className="text-yellow-600">
            Warnings: {summary.warnings}
          </span>
          <span className="text-blue-600">
            Info: {summary.info}
          </span>
        </div>

        {/* Filter Buttons */}
        <div className="flex space-x-2">
          {(['all', 'error', 'warn', 'info'] as const).map((level) => (
            <button
              key={level}
              onClick={() => setFilter(level)}
              className={`
                px-3 py-1 text-xs rounded transition-colors
                ${filter === level
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }
              `}
            >
              {level === 'all' ? 'All' : level.charAt(0).toUpperCase() + level.slice(1)}
              {level !== 'all' && (
                <span className="ml-1">
                  ({level === 'error' ? summary.errors :
                    level === 'warn' ? summary.warnings : summary.info})
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Issues List */}
      <div className="flex-1 overflow-y-auto p-4">
        {filteredIssues.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            {filter === 'all' ? (
              <div>
                <div className="text-2xl mb-2">✅</div>
                <div className="text-lg mb-1">No Issues Found</div>
                <div className="text-sm">Your workflow looks good!</div>
              </div>
            ) : (
              <div>No {filter} level issues found</div>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredIssues.map((issue, index) => (
              <IssueItem
                key={`${issue.code}-${index}`}
                issue={issue}
                onClick={onIssueClick}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {lintResults.workflow_name && (
        <div className="p-3 border-t bg-gray-50 text-xs text-gray-600">
          Workflow: {lintResults.workflow_name} v{lintResults.workflow_version}
        </div>
      )}
    </div>
  );
};

export default IssuesPanel;