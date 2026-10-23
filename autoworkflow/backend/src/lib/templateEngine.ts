import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import type { WorkflowDefinition } from '../types';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface TemplateParameter {
  type: string;
  description: string;
  default?: any;
}

export interface WorkflowTemplate {
  name: string;
  description: string;
  version: string;
  category: string;
  parameters: Record<string, TemplateParameter>;
  workflow: WorkflowDefinition;
}

export class TemplateEngine {
  private templatesDir: string;

  constructor(templatesDir?: string) {
    if (templatesDir) {
      this.templatesDir = templatesDir;
    } else {
      this.templatesDir = path.join(__dirname, '../../templates');
    }
  }

  // 获取所有模板列表
  async listTemplates(): Promise<Array<{ id: string; name: string; description: string; category: string }>> {
    const templates: Array<{ id: string; name: string; description: string; category: string }> = [];

    try {
      const files = await fs.promises.readdir(this.templatesDir);

      for (const file of files) {
        if (file.endsWith('.json')) {
          try {
            const templatePath = path.join(this.templatesDir, file);
            const content = await fs.promises.readFile(templatePath, 'utf8');
            const template: WorkflowTemplate = JSON.parse(content);

            templates.push({
              id: path.basename(file, '.json'),
              name: template.name,
              description: template.description,
              category: template.category
            });
          } catch (error) {
            console.warn(`Failed to parse template ${file}:`, error);
          }
        }
      }
    } catch (error) {
      console.error('Failed to read templates directory:', error);
    }

    return templates;
  }

  // 获取特定模板
  async getTemplate(templateId: string): Promise<WorkflowTemplate | null> {
    try {
      const templatePath = path.join(this.templatesDir, `${templateId}.json`);
      const content = await fs.promises.readFile(templatePath, 'utf8');
      return JSON.parse(content);
    } catch (error) {
      return null;
    }
  }

  // 生成工作流（使用模板+参数）
  async generateWorkflow(templateId: string, parameters: Record<string, any>): Promise<WorkflowDefinition | null> {
    const template = await this.getTemplate(templateId);
    if (!template) {
      return null;
    }

    // 合并默认参数和用户参数
    const mergedParams = { ...this.getDefaultParameters(template), ...parameters };

    // 渲染模板
    const renderedWorkflow = this.renderTemplate(template.workflow, mergedParams);

    return renderedWorkflow;
  }

  // 获取模板的默认参数
  private getDefaultParameters(template: WorkflowTemplate): Record<string, any> {
    const defaults: Record<string, any> = {};

    for (const [key, param] of Object.entries(template.parameters)) {
      if (param.default !== undefined) {
        defaults[key] = param.default;
      }
    }

    return defaults;
  }

  // 模板渲染（简单的字符串替换）
  private renderTemplate(obj: any, parameters: Record<string, any>): any {
    if (typeof obj === 'string') {
      return this.replaceVariables(obj, parameters);
    } else if (Array.isArray(obj)) {
      return obj.map(item => this.renderTemplate(item, parameters));
    } else if (obj && typeof obj === 'object') {
      const result: any = {};
      for (const [key, value] of Object.entries(obj)) {
        result[key] = this.renderTemplate(value, parameters);
      }
      return result;
    }

    return obj;
  }

  // 变量替换
  private replaceVariables(text: string, parameters: Record<string, any>): string {
    return text.replace(/\{\{(\w+)\}\}/g, (match, varName) => {
      return parameters[varName] !== undefined ? String(parameters[varName]) : match;
    });
  }

  // 验证参数
  validateParameters(template: WorkflowTemplate, parameters: Record<string, any>): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    // 检查必需参数
    for (const [key, param] of Object.entries(template.parameters)) {
      if (param.default === undefined && parameters[key] === undefined) {
        errors.push(`Missing required parameter: ${key}`);
      }

      // 类型检查
      if (parameters[key] !== undefined) {
        const value = parameters[key];
        const expectedType = param.type;

        if (expectedType === 'string' && typeof value !== 'string') {
          errors.push(`Parameter ${key} should be a string`);
        } else if (expectedType === 'number' && typeof value !== 'number') {
          errors.push(`Parameter ${key} should be a number`);
        } else if (expectedType === 'boolean' && typeof value !== 'boolean') {
          errors.push(`Parameter ${key} should be a boolean`);
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors
    };
  }

  // 保存新模板
  async saveTemplate(templateId: string, template: WorkflowTemplate): Promise<boolean> {
    try {
      const templatePath = path.join(this.templatesDir, `${templateId}.json`);
      await fs.promises.writeFile(templatePath, JSON.stringify(template, null, 2));
      return true;
    } catch (error) {
      console.error('Failed to save template:', error);
      return false;
    }
  }

  // 删除模板
  async deleteTemplate(templateId: string): Promise<boolean> {
    try {
      const templatePath = path.join(this.templatesDir, `${templateId}.json`);
      await fs.promises.unlink(templatePath);
      return true;
    } catch (error) {
      console.error('Failed to delete template:', error);
      return false;
    }
  }
}

export const templateEngine = new TemplateEngine();