package {{APPLICATION_ID}}.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import {{APPLICATION_ID}}.BuildConfig
import {{APPLICATION_ID}}.R
import {{APPLICATION_ID}}.bridge.CommandServer
import {{APPLICATION_ID}}.bridge.NativeBridge

/**
 * Owns [CommandServer]'s lifetime and keeps the process in the foreground while it
 * is reachable at 127.0.0.1 -- so an agent driving the shell over HTTP is not
 * fighting Android's background-execution limits mid-command.
 *
 * mediaPlayback is the correct declared type: the whole point of this shell is a
 * page that plays audio, and Android 14+ (API 34) rejects a foreground service
 * start whose declared type does not match what it actually does.
 *
 * Started from MainActivity.onCreate() and stopped from onDestroy() -- see the
 * MainActivity overlay. Not bound: nothing outside this process talks to it
 * directly, everything goes through the HTTP server it starts.
 */
class ShellForegroundService : Service() {

    private var commandServer: CommandServer? = null

    override fun onCreate() {
        super.onCreate()
        // Set before anything can call NativeBridge.observe(), which needs a
        // Context to reach filesDir and has no other way to get one.
        NativeBridge.appContext = applicationContext
        createNotificationChannel()
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(
                if (BuildConfig.DEBUG) "Command server listening on 127.0.0.1:${BuildConfig.SAG_PORT}"
                else "Running",
            )
            .setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        commandServer = CommandServer(applicationContext).also { it.start() }
    }

    override fun onDestroy() {
        commandServer?.stop()
        commandServer = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Web shell command server",
            NotificationManager.IMPORTANCE_LOW,
        )
        getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "web_shell_command_server"
        private const val NOTIFICATION_ID = 1

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, ShellForegroundService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, ShellForegroundService::class.java))
        }
    }
}
