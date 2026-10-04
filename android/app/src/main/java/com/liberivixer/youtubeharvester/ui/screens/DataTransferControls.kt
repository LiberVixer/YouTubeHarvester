package com.liberivixer.youtubeharvester.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FileUpload
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.SecureFlagPolicy
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.R

@Composable
internal fun DataTransferControls(viewModel: AppViewModel, busy: Boolean, message: String) {
    var exportDialog by remember { mutableStateOf<Boolean?>(null) }
    var importUri by remember { mutableStateOf<Uri?>(null) }
    var exportPassword by remember { mutableStateOf<CharArray?>(null) }
    val exportPicker = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        val password = exportPassword
        exportPassword = null
        if (uri != null && password != null) viewModel.exportData(uri, password) else password?.fill('\u0000')
    }
    val importPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) { importUri = uri; exportDialog = false }
    }
    DisposableEffect(Unit) { onDispose { exportPassword?.fill('\u0000') } }
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = { exportDialog = true }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Default.FileUpload, contentDescription = null)
            Text(stringResource(R.string.transfer_export), Modifier.padding(start = 8.dp))
        }
        OutlinedButton(onClick = { importPicker.launch(arrayOf("application/octet-stream", "*/*")) },
            enabled = !busy, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Default.FileDownload, contentDescription = null)
            Text(stringResource(R.string.transfer_import), Modifier.padding(start = 8.dp))
        }
        if (busy) CircularProgressIndicator()
        DataTransferResult(message)
    }
    exportDialog?.let { exporting ->
        TransferPasswordDialog(exporting, onDismiss = { exportDialog = null; importUri = null }) { password ->
            exportDialog = null
            if (exporting) {
                exportPassword?.fill('\u0000')
                exportPassword = password
                exportPicker.launch("YouTubeHarvester-transfer.ythbackup")
            } else {
                importUri?.let { viewModel.importData(it, password) } ?: password.fill('\u0000')
                importUri = null
            }
        }
    }
}

@Composable
internal fun DataTransferResult(message: String) {
    if (message.isNotBlank()) Text(message,
        modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite },
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
internal fun TransferPasswordDialog(exporting: Boolean, onDismiss: () -> Unit, onConfirm: (CharArray) -> Unit) {
    // Password text is intentionally not saveable in Activity saved state.
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    val valid = password.length in 12..1024 && (!exporting || password == confirmation)
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(stringResource(if (exporting) R.string.transfer_export else R.string.transfer_import)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(stringResource(if (exporting) R.string.transfer_export_warning else R.string.transfer_import_warning))
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = password, onValueChange = { if (it.length <= 1024) password = it },
                    label = { Text(stringResource(R.string.transfer_password)) },
                    visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
                if (exporting) {
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(value = confirmation, onValueChange = { if (it.length <= 1024) confirmation = it },
                        label = { Text(stringResource(R.string.transfer_password_repeat)) },
                        visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
                }
            }
        },
        confirmButton = {
            TextButton(enabled = valid, onClick = {
                val chars = password.toCharArray()
                password = ""; confirmation = ""
                onConfirm(chars)
            }) { Text(stringResource(if (exporting) R.string.transfer_export else R.string.transfer_import)) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } },
        properties = DialogProperties(securePolicy = SecureFlagPolicy.SecureOn))
}
