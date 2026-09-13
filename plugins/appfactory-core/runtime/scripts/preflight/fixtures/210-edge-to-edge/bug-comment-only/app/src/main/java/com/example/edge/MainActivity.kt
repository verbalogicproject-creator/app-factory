package com.example.edge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // TODO: call enableEdgeToEdge() before setContent once we do the inset
        // work. A comment is not a call.
        /* enableEdgeToEdge() */
        setContent {
            HomeScreen()
        }
    }
}
