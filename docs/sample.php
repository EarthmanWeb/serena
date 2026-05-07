<?php
/**
 * Iconic Builder Shortcodes
 *
 * Implements shortcodes for the Iconic Builder builder
 *
 * @package Iconic_Builder
 */

// Prevent direct access
if ( ! defined( 'ABSPATH' ) ) {
  exit;
}

/**
 * Class Iconic_Builder_Shortcodes
 *
 * Handles all shortcode functionality for the Iconic Builder plugin
 */
class Iconic_Builder_Shortcodes {
  /**
   * Blade engine instance
   *
   * @var Iconic_Builder_Blade_Engine
   */
  private $blade;

  /**
   * Parser instance
   *
   * @var Iconic_Builder_Shortcode_Parser
   */
  private $parser;

  /**
   * Container grouping state tracker
   *
   * @var array
   */
  private static $group_sections_remaining = 0;
  private static $section_index            = 0;
  private static $section_ids              = array();
  private static $inside_group_counter     = 0;

  /**
   * Get Blade engine instance
   *
   * @return Iconic_Builder_Blade_Engine|null
   */
  public function get_blade() {
    return $this->blade;
  }

  /**
   * Register built-in Blade functions
   */
  private function register_blade_functions() {
    // Blade functions are handled through the Blade engine
    // This method is kept for any future built-in functions
  }

  /**
   * Constructor
   */
  public function __construct() {
    // // Initialize tooltips handler
    if ( ! class_exists( 'Iconic_Builder_Tooltips' ) ) {
      require_once ICONIC_BUILDER_PATH . 'includes/class-builder-tooltips.php';
    }

    // Initialize parser
    if ( ! class_exists( 'Iconic_Builder_Shortcode_Parser' ) ) {
      require_once ICONIC_BUILDER_PATH . 'includes/class-builder-shortcode-parser.php';
    }
    $this->parser = new Iconic_Builder_Shortcode_Parser();

    // All background wrapper functionality now handled directly in this class
    // Load Block Sources first (required by Blade Engine)
    if ( ! class_exists( 'Iconic_Builder_Block_Sources' ) ) {
      require_once ICONIC_BUILDER_PATH . 'includes/class-block-sources.php';
    }

    // Initialize Blade engine
    if ( ! class_exists( 'Iconic_Builder_Blade_Engine' ) ) {
      require_once ICONIC_BUILDER_PATH . 'includes/class-blade-engine.php';
    }
    $this->blade = new Iconic_Builder_Blade_Engine();

    // Register built-in Blade functions
    $this->register_blade_functions();

    // Apply filter to allow other classes to register Blade functions
    $blade_functions = apply_filters( 'ico_blade_functions', array() );
    // This is kept for future extensibility

    // Register shortcodes
    add_shortcode( 'section', array( $this, 'handle_section_shortcode' ) );

    // Remove the wptexturize filter to fix json parsing
    remove_filter( 'the_content', 'wptexturize' );

    // Process content early before wpautop
    add_filter( 'the_content', array( $this, 'prepare_content_for_shortcodes' ), 1 );

    // Process content late to clean up after shortcodes are processed
    add_filter( 'the_content', array( $this, 'cleanup_content' ), 999 );

    remove_filter( 'the_content', 'wpautop' );
    add_filter( 'the_content', 'wpautop', 99 );
    add_filter( 'the_content', 'shortcode_unautop', 100 );
  }

  /**
   * Section shortcode handler
   *
   * Parses the section shortcode with nested data, settings, and content tags
   * Renders the appropriate template part based on section type
   *
   * Usage:
   * [section type="html" id="1234_abcd"]
   *  [settings]{"section_classes":"my-class","section_custom_css":""}[/settings]
   *  [data]{"html_label":"My Title","html_description":"<p>Content here</p>"}[/data]
   *  [content]<p>Optional inner content</p>[/content]
   * [/section]
   *
   * @param array  $atts Shortcode attributes
   * @param string $content Shortcode content
   * @return string Rendered HTML output
   */
  public function handle_section_shortcode( $atts, $content = null ) {
    // Get shortcode attributes
    $atts = shortcode_atts(
      array(
        'type'   => '',        // Type of section
        'id'     => '',        // Unique section ID
        'header' => '', // Field to use for header/title
      ),
      $atts,
      'section'
    );

    // If no type is specified, return nothing
    if ( empty( $atts['type'] ) ) {
      return '';
    }

    // Initialize args array with section ID and type
    $args = array(
      'section_id'   => $atts['id'],
      'section_type' => $atts['type'],
    );

    // Add section index for logged-in users
    if ( is_user_logged_in() ) {
      $args['section_index'] = $this->get_section_index( $atts['id'], $content );
    }

    // Parse flat JSON from shortcode content
    $flat_data = $this->parser->parse_flat_json_from_content( $content );

    if ( ! empty( $flat_data ) ) {
      // Apply text processing to all fields
      $flat_data = $this->parser->apply_text_processing_to_data( $flat_data );

      // Merge ALL fields directly into $args at root level
      $args = array_merge( $args, $flat_data );

      // Process all fields (styling, computed classes, etc.)
      // ONLY separates group_ prefixed fields from block fields
      $args = $this->parser->process_all_fields( $args );

      // Create clean template variables for classes
      if ( ! empty( $args['content_classes_block'] ) ) {
        $args['content_classes'] = implode( ' ', $args['content_classes_block'] );
      }
      if ( ! empty( $args['lead_classes_block'] ) ) {
        $args['lead_classes'] = implode( ' ', $args['lead_classes_block'] );
      }
      if ( ! empty( $args['footer_classes_block'] ) ) {
        $args['footer_classes'] = implode( ' ', $args['footer_classes_block'] );
      }
      if ( ! empty( $args['classes_block'] ) ) {
        $args['block_classes'] = implode( ' ', $args['classes_block'] );
      }

      // Handle header field for section ID generation
      if ( ! empty( $atts['header'] ) && ! empty( $flat_data[ $atts['header'] ] ) ) {
        $slug = $this->generate_slug_from_title( $flat_data[ $atts['header'] ] );
        if ( ! empty( $slug ) ) {
          $args['section_id'] = $slug;
        }
      }
    }

    // Generate template path based on section type
    $template_part = 'template-parts/blocks/' . $atts['type'] . '/' . $atts['type'];

    // Allow filtering of template path
    $template_part = apply_filters( 'ico_builder_section_template_part', $template_part, $atts['type'], $args );

    // Set section index
    ++self::$section_index;

    // Set group wrapper settings from flat $args
    $group_blocks   = ! empty( $args['group_additional_blocks'] ) ? (int) $args['group_additional_blocks'] : 0;
    $starting_group = $group_blocks > 0 && self::$group_sections_remaining == 0;
    $in_group       = self::$group_sections_remaining > 0 || $starting_group;

    // Set section_index to match backend and to be used in tooltips
    $args['section_index'] = $atts['type'] . '-' . self::$section_index;

    // Set a unique section id dynamically from row_header field
    // Get block config to find which field has row_header=true
    $block_config = $this->get_block_config( $atts['type'] );
    $row_header_field = null;

    // Check all tabs for row_header field
    if ( ! empty( $block_config ) && is_array( $block_config ) ) {
      foreach ( $block_config as $tab_key => $tab_data ) {
        if ( is_array( $tab_data ) ) {
          foreach ( $tab_data as $field_key => $field_config ) {
            if ( is_array( $field_config ) && ! empty( $field_config['row_header'] ) ) {
              $row_header_field = $field_key;
              break 2;
            }
          }
        }
      }
    }

    // Generate section_id based on row_header field value if available
    if ( ! empty( $row_header_field ) && ! empty( $flat_data[ $row_header_field ] ) ) {
      $args['section_id'] = $this->generate_slug_from_title( $flat_data[ $row_header_field ] );
    } elseif ( ! empty( $args['block_title'] ) ) {
      // Fallback to block_title for backward compatibility
      $args['section_id'] = $this->generate_slug_from_title( $args['block_title'] );
    } else {
      // Final fallback to block type
      $args['section_id'] = $atts['type'];
    }

    // Check for duplicate IDs - track both regular sections and groups with -AddGroup suffix
    // Groups need their -AddGroup suffix tracked separately for uniqueness
    $tracking_id = $starting_group ? $args['section_id'] . '-AddGroup' : $args['section_id'];

    // check if this ID already existed in the page, if so, add a number to the end
    if ( isset( self::$section_ids[ $tracking_id ] ) ) {
      self::$section_ids[ $tracking_id ]++;
      $unique_suffix = '-' . self::$section_ids[ $tracking_id ];
    } else {
      self::$section_ids[ $tracking_id ] = 0;
      $unique_suffix                      = '';
    }

    // Apply the unique suffix to the section_id
    $args['section_id'] = $args['section_id'] . $unique_suffix;

    // increment inside group counter only if we're in a group
    if ( $in_group ) {
      // Reset counter when starting a new group
      if ( $starting_group ) {
        self::$inside_group_counter = 0;
      }
      self::$inside_group_counter++;
      $args['inside_group'] = self::$inside_group_counter;
    } else {
      // Not in a group, set to 0
      $args['inside_group'] = 0;
    }

    // Start group wrapper (with styling)
    if ( $starting_group ) {
      // Group wrapper gets -AddGroup suffix plus any unique suffix
      $group_wrapper_id = $args['section_id'] . '-AddGroup';
      $this->output_wrapper( $group_wrapper_id, $args );
      self::$group_sections_remaining = $group_blocks;
    }

    // Always output individual wrapper (block never gets -AddGroup)
    $this->output_wrapper( $args['section_id'], $args );

    // Output edit link for logged-in users with edit capability
    $this->output_edit_link( $args['section_index'] );

    // Render template
    $this->render_template( $template_part, $args, $atts );

    // Always close individual wrapper
    echo '</section>';

    // Close group wrapper if group ends
    if ( $in_group && ! $starting_group ) {
      // Only decrement for non-initiating sections
      if ( self::$group_sections_remaining == 1 ) {
        echo '</section>';
      }
      --self::$group_sections_remaining;
    }

    return '';
  }

  /**
   * Update Blade global variables with current section's styling
   *
   * Sets dynamic styling globals that all templates can use without modification
   *
   * @param array $args Section arguments containing styling data
   */
  private function update_blade_styling_globals( $args ) {
    // Blade engine shares global variables automatically
    // Styling is passed directly through the $args array
  }

  /**
   * Load a template file with custom path
   *
   * PHP preprocessor is OPTIONAL:
   * 1. If block-name.php exists: include it (preprocessor calls Blade render)
   * 2. If only block-name.blade.php exists: render directly with Blade
   *
   * @param string $template_file Full path to the template file
   * @param array  $args Arguments to pass to the template
   * @return string|false The output or false on failure
   */
  private function custom_template_loader( $template_part, $args = array(), $atts = array() ) {
    // Try to find PHP preprocessor file
    $template_file = Iconic_Builder_Block_Sources::get_instance()->find_template_file( $atts['type'] );

    if ( $template_file ) {
      // PHP preprocessor exists - include it (will call Blade render internally)
      include $template_file;
      return '';
    }

    // PHP preprocessor not found - try to find Blade template directly
    $blade_file = Iconic_Builder_Block_Sources::get_instance()->find_template_file( $atts['type'], $atts['type'] . '.blade.php' );

    if ( $blade_file ) {
      // Blade template exists - render directly without PHP preprocessor
      echo Blade()->render( $args['section_type'], $args );
      return '';
    }

    // Neither PHP nor Blade template found - show error
    echo '<pre>';
    printf( esc_html__( 'Template not found: %s', 'builder' ), esc_html( $template_part ) );
    echo '';
    echo 'Section Type: ' . esc_html( $atts['type'] ) . '';
    echo 'Section ID: ' . esc_html( $atts['id'] ) . '';
    echo 'Section Args: <pre>' . esc_html( print_r( $args, true ) ) . '</pre>' . '';

    // Output content if available
    if ( ! empty( $args['content'] ) ) {
      echo 'Content: ' . esc_html( $args['content'] ) . '';
    }
    echo '</pre>';
    return '';
  }

  /**
   * Render template
   *
   * @param string $template_part Template part path
   * @param array  $args Args array
   * @param array  $atts Original shortcode attributes
   * @return string Rendered HTML
   */
  private function render_template( $template_part, $args, $atts ) {
    // Update Blade globals with current section's background styling
    $this->update_blade_styling_globals( $args );

    return $this->custom_template_loader( $template_part, $args, $atts );
  }

  /**
   * Prepare content for shortcode parsing
   *
   * Strips newlines from content before WordPress processes shortcodes
   * to prevent issues with JSON parsing in shortcodes
   *
   * @param string $content The post content
   * @return string Modified content
   */
  public function prepare_content_for_shortcodes( $content ) {
    // Only process if content contains our shortcode and we're on a page
    if ( strpos( $content, '[section' ) !== false && ( is_page() || 'page' === get_post_type() ) ) {
      // Remove all newlines from the entire content except within shortcode blocks
      // This prevents WordPress from creating <p><br></p> tags
      $pieces = preg_split( '/(\[section.*?\].*?\[\/section\])/s', $content, -1, PREG_SPLIT_DELIM_CAPTURE );

      $cleaned_content = '';
      foreach ( $pieces as $piece ) {
        if ( strpos( $piece, '[section' ) === 0 ) {
          // This is a section shortcode - keep it as is
          $cleaned_content .= $piece;
        } else {
          // This is content outside a section - remove all newlines
          $cleaned = str_replace( array( "\r\n", "\r", "\n" ), ' ', $piece );
          // Also remove multiple spaces
          $cleaned          = preg_replace( '/\s+/', ' ', $cleaned );
          $cleaned_content .= $cleaned;
        }
      }
      $content = $cleaned_content;
    }

    return $content;
  }

  /**
   * Clean up content after shortcode processing
   *
   * Removes unwanted HTML comments and empty paragraphs
   *
   * @param string $content The processed content
   * @return string The cleaned content
   */
  public function cleanup_content( $content ) {
    // Only process pages
    if ( is_page() || 'page' === get_post_type() ) {
      // Close any remaining open container groups
      // Group closing is handled in handle_section_shortcode now
      // First pass: Remove all HTML comments
      $content = preg_replace( '/<!--.*?-->/s', '', $content );

      // Second pass: Remove all paragraph tags that contain only whitespace or breaks
      $content = preg_replace( '/<p>(\s|&nbsp;|<br\s*\/?>)*<\/p>/is', '', $content );

      // Third pass: Remove paragraph tags wrapping section tags
      $content = preg_replace( '/<p>\s*(<section)/is', '$1', $content );
      $content = preg_replace( '/(<\/section>)\s*<\/p>/is', '$1', $content );

      // Fourth pass: Remove empty space between sections
      $content = preg_replace( '/(<\/section>)\s+(<section)/is', '$1$2', $content );

      // Fifth pass: Clean up any double spaces
      $content = preg_replace( '/\s{2,}/', ' ', $content );
    }

    return $content;
  }

  /**
   * Generate a URL-friendly slug from a title
   *
   * @param string $title The title to convert to a slug
   * @return string The generated slug
   */
  private function generate_slug_from_title( $title ) {
    if ( empty( $title ) ) {
      return '';
    }

    $slug = sanitize_title( $title );

    return $slug;
  }

  /**
   * Get block configuration from JSON file
   * Loads block definition to discover tabs dynamically
   *
   * @param string $block_type Block name/type
   * @return array Block configuration with tabs
   */
  private function get_block_config( $block_type ) {
    // Try to get from section component if available
    global $ico_builder_sections;
    if ( isset( $ico_builder_sections ) && method_exists( $ico_builder_sections, 'get_section' ) ) {
      $section = $ico_builder_sections->get_section( $block_type );
      if ( $section ) {
        return $section;
      }
    }

    // Fallback: Use Block Sources to find JSON file
    $block_sources = Iconic_Builder_Block_Sources::get_instance();
    $block_paths = $block_sources->get_block_paths( true );

    foreach ( $block_paths as $path ) {
      $json_file = $path . '/' . $block_type . '/' . $block_type . '.json';
      if ( file_exists( $json_file ) ) {
        $config = json_decode( file_get_contents( $json_file ), true );
        if ( json_last_error() === JSON_ERROR_NONE ) {
          return $config;
        }
      }
    }

    // Default config if not found - use new property names
    return array(
      'tabs' => array(
        'content'        => 'Content',
        'design'         => 'Design',
        'advanced|admin' => 'Advanced',
      ),
    );
  }

  /**
   * Get section index based on position in content
   *
   * @param string $section_id The section ID
   * @param string $full_content The full post content
   * @return int The section index (1-based)
   */
  private function get_section_index( $section_id, $full_content ) {
    global $post;

    if ( ! $post ) {
      return 1;
    }

    $content = get_post_field( 'post_content', $post->ID );
    $index   = 1;

    // Find all section shortcodes in order
    preg_match_all( '/\[section[^\]]*id="([^"]+)"[^\]]*\]/', $content, $matches, PREG_OFFSET_CAPTURE );

    if ( ! empty( $matches[1] ) ) {
      foreach ( $matches[1] as $i => $match ) {
        if ( $match[0] === $section_id ) {
          $index = $i + 1;
          break;
        }
      }
    }

    return $index;
  }

  /**
   * Output wrapper with computed styling from process functions
   *
   * @param string $wrapper_id Wrapper ID
   * @param array  $args Section arguments with computed data
   */
  private function output_wrapper( $wrapper_id, $args ) {
    $wrapper_parts = array();

    // Determine wrapper type and normalize ID
    $is_group        = strpos( $wrapper_id, '-AddGroup' ) > 0;
    $data_name       = $is_group ? 'group' : 'block';
    $wrapper_id      = str_replace( '-AddGroup', '-group', $wrapper_id );
    $wrapper_parts[] = '<section';
    $wrapper_parts[] = ' id="' . esc_attr( $wrapper_id ) . '"';

    // Initialize arrays for wrapper attributes
    $classes         = array();
    $data_attributes = array();
    $inline_styles   = array();

    // Assemble wrapper attributes based on type - access flat $args with context prefixes
    if ( $is_group ) {
      // Group wrapper uses group data
      $classes[] = 'block-group';

      // Merge ONLY group-specific data (NO block styling)
      if ( ! empty( $args['classes_group'] ) ) {
        $classes = array_merge( $classes, $args['classes_group'] );
      }
      if ( ! empty( $args['data_attributes_group'] ) ) {
        $data_attributes = array_merge( $data_attributes, $args['data_attributes_group'] );
      }
      if ( ! empty( $args['css_vars_group'] ) ) {
        $inline_styles = array_merge( $inline_styles, $args['css_vars_group'] );
      }
      if ( ! empty( $args['inline_styles_group'] ) ) {
        $inline_styles = array_merge( $inline_styles, $args['inline_styles_group'] );
      }
      // Group wrapper only uses group-specific data

    } else {
      // Block wrapper uses data from flat field processing
      $classes[] = 'block block-' . esc_attr( $args['section_type'] );

      // Merge all block classes (class_ fields + section_classes)
      if ( ! empty( $args['classes_block'] ) ) {
        $classes = array_merge( $classes, $args['classes_block'] );
      }

      // Merge data attributes (from background processing)
      if ( ! empty( $args['data_attributes_block'] ) ) {
        $data_attributes = array_merge( $data_attributes, $args['data_attributes_block'] );
      }

      // Merge all inline styles (CSS vars + style_ fields + section_custom_css)
      if ( ! empty( $args['css_vars_block'] ) ) {
        $inline_styles = array_merge( $inline_styles, $args['css_vars_block'] );
      }
      if ( ! empty( $args['inline_styles_block'] ) ) {
        $inline_styles = array_merge( $inline_styles, $args['inline_styles_block'] );
      }

      // Add block-specific data attribute
      $wrapper_parts[] = ' data-block-type="' . esc_attr( $args['section_type'] ) . '"';
    }

    // Apply tooltip attributes (modifies classes and data_attributes arrays)
    if ($data_name === 'group') {
      // Group wrapper
      $tooltip_id = self::$section_index . "<br><sup>(group)</sup>";
      list( $classes, $data_attributes ) = Iconic_Builder_Tooltips::apply_tooltip_attributes( $classes, $data_attributes, $tooltip_id, $args, self::$section_index );
    } elseif ($args['inside_group'] > 0) {
      // Inner blocks (all blocks inside a group)
      $tooltip_id = self::$section_index . "<br><sup>(inner)</sup>";
      list( $classes, $data_attributes ) = Iconic_Builder_Tooltips::apply_tooltip_attributes( $classes, $data_attributes, $tooltip_id, $args, self::$section_index );
    } else {
      // Standalone blocks (not in a group)
      $tooltip_id = self::$section_index;
      list( $classes, $data_attributes ) = Iconic_Builder_Tooltips::apply_tooltip_attributes( $classes, $data_attributes, $tooltip_id, $args, self::$section_index );
    }

    // Output classes AFTER tooltip modifications
    $wrapper_parts[] = ' class="' . esc_attr( implode( ' ', array_unique( $classes ) ) ) . '"';

    // Output section type data attribute
    $wrapper_parts[] = ' data-section-type="' . esc_attr( $data_name ) . '"';

    // Output builder index data attribute
    $wrapper_parts[] = ' data-builder-index="' . esc_attr( $args['section_index'] ) . '"';

    // Output data attributes AFTER tooltip modifications
    if ( ! empty( $data_attributes ) ) {
      $wrapper_parts[] = ' ' . implode( ' ', $data_attributes );
    }

    // Output all inline styles (CSS vars + style_ fields)
    if ( ! empty( $inline_styles ) ) {
      $wrapper_parts[] = ' style="' . esc_attr( implode( '; ', $inline_styles ) ) . '"';
    }

    $wrapper_parts[] = '>';

    echo implode( '', $wrapper_parts );
  }

  /**
   * Output edit link for block (gear icon at top-right on hover)
   *
   * @param string $section_index Section index (e.g., "team-grid-1")
   */
  private function output_edit_link( $section_index ) {
    if ( ! current_user_can( 'edit_post', get_the_ID() ) ) {
      return;
    }

    $edit_url = add_query_arg( 'open', 'row-' . $section_index, get_edit_post_link( get_the_ID(), 'raw' ) );

    printf(
      '<a href="%s" class="block-edit-link" title="%s"><i class="fa-solid fa-pencil"></i></a>',
      esc_url( $edit_url ),
      esc_attr__( 'Edit this block', 'iconic-builder' )
    );
  }

}

// Initialize the shortcodes class
if ( ! is_admin() ) {
  // Initialize shortcodes class (which will apply the ico_blade_functions filter)
  // Note: Blade functions are initialized in builder-loader.php
  $ico_builder_shortcodes = new Iconic_Builder_Shortcodes();
}
