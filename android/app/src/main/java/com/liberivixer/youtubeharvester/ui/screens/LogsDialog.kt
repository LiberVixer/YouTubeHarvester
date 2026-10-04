package com.liberivixer.youtubeharvester.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liberivixer.youtubeharvester.R

@Composable
fun LogsDialog(
    logText: String,
    loading: Boolean,
    error: String?,
    retentionDays: Int,
    onRefresh: () -> Unit,
    onClear: () -> Unit,
    onRetentionChanged: (Int) -> Unit,
    onShare: () -> Unit,
    onDismiss: () -> Unit,
) {
    var confirmClear by remember { mutableStateOf(false) }
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text(stringResource(R.string.clear_logs_confirm_title)) },
            text = { Text(stringResource(R.string.clear_logs_confirm_message)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmClear = false
                        onClear()
                    },
                ) { Text(stringResource(R.string.clear_logs)) }
            },
            dismissButton = {
                TextButton(onClick = { confirmClear = false }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.application_logs)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    RetentionMenu(retentionDays, onRetentionChanged)
                    Row {
                        IconButton(onClick = onRefresh, enabled = !loading) {
                            Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                        }
                        IconButton(onClick = { confirmClear = true }, enabled = logText.isNotEmpty() && !loading) {
                            Icon(Icons.Default.DeleteOutline, contentDescription = stringResource(R.string.clear_logs))
                        }
                    }
                }
                Surface(
                    modifier = Modifier.fillMaxWidth().heightIn(min = 220.dp, max = 460.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = MaterialTheme.shapes.small,
                ) {
                    Box(modifier = Modifier.padding(12.dp), contentAlignment = Alignment.Center) {
                        when {
                            loading -> CircularProgressIndicator(modifier = Modifier.size(34.dp))
                            error != null -> Text(error, color = MaterialTheme.colorScheme.error)
                            logText.isBlank() -> Text(
                                stringResource(R.string.log_empty),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            else -> SelectionContainer {
                                Text(
                                    text = logText,
                                    modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = 11.sp,
                                    lineHeight = 15.sp,
                                )
                            }
                        }
                    }
                }
                Text(
                    stringResource(R.string.logs_private_hint),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onShare, enabled = logText.isNotBlank()) {
                Icon(Icons.Default.Share, contentDescription = null)
                Spacer(Modifier.size(5.dp))
                Text(stringResource(R.string.share_logs))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.close)) }
        },
    )
}

@Composable
private fun RetentionMenu(retentionDays: Int, onRetentionChanged: (Int) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }) {
            Text(pluralStringResource(R.plurals.logs_retention_value, retentionDays, retentionDays))
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            listOf(1, 3, 7, 14, 30).forEach { days ->
                DropdownMenuItem(
                    text = { Text(pluralStringResource(R.plurals.logs_retention_value, days, days)) },
                    onClick = {
                        expanded = false
                        onRetentionChanged(days)
                    },
                )
            }
        }
    }
}
