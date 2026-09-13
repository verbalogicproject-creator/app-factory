package com.example.edge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // No enableEdgeToEdge() call -- content draws under the system bars once
        // targetSdk enforces edge-to-edge.
        setContent {
            HomeScreen()
        }
    }
}
