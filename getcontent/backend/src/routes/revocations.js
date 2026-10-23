import express from 'express';
const router = express.Router();

router.get('/revocations', (req,res)=>{
  // MVP: no revocations
  res.json({ revoked: false, reason: null });
});

export default router;