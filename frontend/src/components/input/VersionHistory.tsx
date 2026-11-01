import React, { useState, useEffect } from 'react'
import {
  Box, Typography, Paper, Table, TableBody, TableCell,
  TableHead, TableRow, Chip, CircularProgress, Alert
} from '@mui/material'
import { api } from '../../api/client'

interface Props { companyId: string }

export default function VersionHistory({ companyId }: Props) {
  const [versions, setVersions] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    api.get(`/version/${companyId}`)
      .then(r => setVersions(r.data))
      .catch(() => setVersions([]))
      .finally(() => setLoading(false))
  }, [companyId])

  if (loading) return <CircularProgress size={20} />

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={700} mb={1}>Version History</Typography>
      {versions.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No versions yet</Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>Period</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Version</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Date</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {versions.map(v => (
              <TableRow key={v.version_id}>
                <TableCell>{v.period_label}</TableCell>
                <TableCell>v{v.version_num}</TableCell>
                <TableCell>
                  <Chip
                    label={v.is_active ? 'Active' : 'Archived'}
                    size="small"
                    color={v.is_active ? 'success' : 'default'}
                    sx={{ height: 18, fontSize: 10 }}
                  />
                </TableCell>
                <TableCell sx={{ fontSize: 11, color: 'text.secondary' }}>
                  {new Date(v.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  )
}
