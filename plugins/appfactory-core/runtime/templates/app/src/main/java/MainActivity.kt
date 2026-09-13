package {{APPLICATION_ID}}

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.hilt.navigation.compose.hiltViewModel
import {{APPLICATION_ID}}.ui.HomeScreen
import {{APPLICATION_ID}}.ui.theme.{{APP_CLASS}}Theme
import dagger.hilt.android.AndroidEntryPoint

/**
 * @AndroidEntryPoint is the half of the Hilt contract that fails LOUDLY. The other
 * half is @HiltAndroidApp on the Application class AND android:name in the manifest
 * pointing at it — miss either and this throws at onCreate:
 *
 *     IllegalStateException: Hilt Activity must be attached to an @HiltAndroidApp Application
 *
 * That compiles perfectly and no test can see it. Preflight check 060 exists solely
 * for this, because nine consecutive green builds once shipped it.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Edge-to-edge is mandatory and non-opt-out from targetSdk 35/36: without
        // this call, content draws under the status bar and navigation bar rather
        // than around them. See preflight check 210.
        enableEdgeToEdge()
        setContent {
            {{APP_CLASS}}Theme {
                HomeScreen(
                    versionName = BuildConfig.VERSION_NAME,
                    versionCode = BuildConfig.VERSION_CODE,
                    gitSha = BuildConfig.GIT_SHA,
                )
            }
        }
    }
}
