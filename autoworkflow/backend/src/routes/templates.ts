import express from 'express';
import { templateEngine } from '../lib/templateEngine';
import { loadActionSchemas } from '../lib/ajv';
import { WorkflowLinter } from '../lib/linter';

const router = express.Router();

// GET /templates - 获取所有模板列表
router.get('/', async (req, res) => {
  try {
    const templates = await templateEngine.listTemplates();
    res.json({
      success: true,
      templates
    });
  } catch (error) {
    console.error('Templates list error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to list templates',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// GET /templates/:id - 获取特定模板详情
router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const template = await templateEngine.getTemplate(id);

    if (!template) {
      return res.status(404).json({
        success: false,
        error: 'Template not found'
      });
    }

    res.json({
      success: true,
      template
    });
  } catch (error) {
    console.error('Template get error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get template',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// POST /templates/:id/generate - 使用模板生成工作流
router.post('/:id/generate', async (req, res) => {
  try {
    const { id } = req.params;
    const parameters = req.body.parameters || {};

    // 获取模板
    const template = await templateEngine.getTemplate(id);
    if (!template) {
      return res.status(404).json({
        success: false,
        error: 'Template not found'
      });
    }

    // 验证参数
    const validation = templateEngine.validateParameters(template, parameters);
    if (!validation.valid) {
      return res.status(400).json({
        success: false,
        error: 'Invalid parameters',
        details: validation.errors
      });
    }

    // 生成工作流
    const workflow = await templateEngine.generateWorkflow(id, parameters);
    if (!workflow) {
      return res.status(500).json({
        success: false,
        error: 'Failed to generate workflow'
      });
    }

    // 可选：验证生成的工作流
    if (req.body.validate !== false) {
      const actionSchemas = loadActionSchemas();
      const linter = new WorkflowLinter(actionSchemas);
      const issues = linter.lint(workflow);

      res.json({
        success: true,
        workflow,
        validation: {
          issues: issues.length,
          details: issues
        }
      });
    } else {
      res.json({
        success: true,
        workflow
      });
    }

  } catch (error) {
    console.error('Template generate error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate workflow from template',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// POST /templates - 创建新模板
router.post('/', async (req, res) => {
  try {
    const { id, template } = req.body;

    if (!id || !template) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: id, template'
      });
    }

    // 验证模板结构
    if (!template.name || !template.description || !template.workflow) {
      return res.status(400).json({
        success: false,
        error: 'Invalid template structure. Required: name, description, workflow'
      });
    }

    const success = await templateEngine.saveTemplate(id, template);
    if (!success) {
      return res.status(500).json({
        success: false,
        error: 'Failed to save template'
      });
    }

    res.json({
      success: true,
      message: 'Template saved successfully'
    });

  } catch (error) {
    console.error('Template save error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to save template',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// PUT /templates/:id - 更新模板
router.put('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const template = req.body;

    // 验证模板结构
    if (!template.name || !template.description || !template.workflow) {
      return res.status(400).json({
        success: false,
        error: 'Invalid template structure. Required: name, description, workflow'
      });
    }

    const success = await templateEngine.saveTemplate(id, template);
    if (!success) {
      return res.status(500).json({
        success: false,
        error: 'Failed to update template'
      });
    }

    res.json({
      success: true,
      message: 'Template updated successfully'
    });

  } catch (error) {
    console.error('Template update error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update template',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// DELETE /templates/:id - 删除模板
router.delete('/:id', async (req, res) => {
  try {
    const { id } = req.params;

    const success = await templateEngine.deleteTemplate(id);
    if (!success) {
      return res.status(500).json({
        success: false,
        error: 'Failed to delete template'
      });
    }

    res.json({
      success: true,
      message: 'Template deleted successfully'
    });

  } catch (error) {
    console.error('Template delete error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete template',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// GET /templates/:id/preview - 预览模板生成的工作流（不实际生成）
router.get('/:id/preview', async (req, res) => {
  try {
    const { id } = req.params;
    const parameters = req.query as Record<string, any>;

    // 获取模板
    const template = await templateEngine.getTemplate(id);
    if (!template) {
      return res.status(404).json({
        success: false,
        error: 'Template not found'
      });
    }

    // 获取默认参数
    const defaultParams: Record<string, any> = {};
    for (const [key, param] of Object.entries(template.parameters)) {
      if (param.default !== undefined) {
        defaultParams[key] = param.default;
      }
    }

    // 合并用户参数
    const mergedParams = { ...defaultParams, ...parameters };

    res.json({
      success: true,
      template: {
        name: template.name,
        description: template.description,
        category: template.category,
        parameters: template.parameters
      },
      preview_parameters: mergedParams,
      parameter_validation: templateEngine.validateParameters(template, mergedParams)
    });

  } catch (error) {
    console.error('Template preview error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to preview template',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

export { router as templatesRouter };